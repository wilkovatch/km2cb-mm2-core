# The potentially visible sets of the city (city/<city>.cpvs), which the game reads at the city load to draw only the
# rooms (and their objects) seen from the current room. The format, as the stock files have it (see the agent
# notes of the core, docs/agents/exporting.md):
# - "PVS0", the number of rooms of the PSDL + 2 (u32), then an offset (u32) for each room and one for the end of the
#   data: where the list of the room starts in the data after the offsets
# - each list has 2 bits for each room of the PSDL, from the low bits of its bytes: the first pair is reserved (room 0,
#   always 0), pair k is the PSDL room k (counting from 1), 3 = visible, 0 = not visible
# - each list is run-length encoded: a byte with the top bit set is followed by (byte & 0x7f) + 1 bytes copied as they
#   are, a byte with the top bit clear by a byte repeated (byte & 0x7f) times (without + 1, unlike the copies)
# The sets are computed on a height field of the occluders (2.5D, see CPVSGenerator): every room sees itself, its
# neighbours and the rooms of which a point is above the horizon of one of its viewpoints.

import math

import numpy as np

from scene import Scene, is_surface, to_writer_space
from .file_io import BinaryFileHelper

HEADER = "PVS0"
VISIBLE = 3


class CPVSParameters:
    def __init__(self, cell, azimuths, max_viewpoints, viewpoint_spacing, eye_heights):
        self.cell = cell  # m, the size of a cell of the height field and the step along the rays
        self.azimuths = azimuths  # the number of rays around each viewpoint
        self.max_viewpoints = max_viewpoints  # per room
        self.viewpoint_spacing = viewpoint_spacing  # m, no more viewpoints when they would be closer than this
        self.eye_heights = eye_heights  # m above the floor
        self.target_cell = 2 * cell  # m, the targets of a room are its highest point in cells of this size
        self.clearance = 3.0  # m, see CPVSGenerator.rasterize_occluders
        self.max_cells = 2048  # along the longest side of the city, the cell is larger in larger cities


# Measured on the stock cities (exporters/psdl/tools/cpvs_check.py --stock, see docs/agents/exporting.md of the core):
# more viewpoints and eye heights find more of the rooms of the stock sets, a finer grid doesn't
FAST = CPVSParameters(cell=4.0, azimuths=360, max_viewpoints=6, viewpoint_spacing=15.0, eye_heights=(3.0, 10.0))
ACCURATE = CPVSParameters(cell=4.0, azimuths=1024, max_viewpoints=64, viewpoint_spacing=4.0, eye_heights=(2.0, 8.0, 20.0))

# the rays step one cell at a time for this many steps, then the steps double each time the distance does
NEAR_STEPS = 128
CHUNK = 32  # steps of all the rays processed together
TARGET_TILE = 64.0  # m, the targets of a room are tested in groups of this size

# the kinds of the occluders: ground (solid below it, walls included; a floor under it more than the clearance lower
# makes a passage), closed (solid down to the ground, like the roofs of the buildings: never a passage)
OCCLUDER_GROUND = 0
OCCLUDER_CLOSED = 1


# --- the lists


def encode_list(visible):
    # the run-length encoded list of a room: visible[k] for each PSDL room k (k = 0 is the reserved pair)
    n = len(visible)
    data = bytearray((n + 3) // 4)
    for k in np.flatnonzero(visible):
        data[k // 4] |= VISIBLE << (2 * (k % 4))
    res = bytearray()
    literal = bytearray()

    def flush_literal():
        while len(literal) > 0:
            chunk = literal[:128]
            res.append(0x80 | (len(chunk) - 1))
            res.extend(chunk)
            del literal[:128]

    i = 0
    while i < len(data):
        j = i
        while j < len(data) and data[j] == data[i] and j - i < 127:
            j += 1
        if j - i >= 3:
            flush_literal()
            res.append(j - i)
            res.append(data[i])
        else:
            literal.extend(data[i:j])
        i = j
    flush_literal()
    return bytes(res)


def decode_list(data):
    # the bytes of a run-length encoded list (shorter than the full list when the game files leave out the last zeros)
    res = bytearray()
    i = 0
    while i < len(data):
        h = data[i]
        i += 1
        if h & 0x80:
            n = (h & 0x7f) + 1
            if i + n > len(data):
                raise Exception("CPVS list truncated in a copy")
            res.extend(data[i:i + n])
            i += n
        else:
            if i >= len(data):
                raise Exception("CPVS list truncated in a repeat")
            res.extend(bytes([data[i]]) * h)
            i += 1
    return bytes(res)


def list_values(data, n):
    # the 2-bit values of the n pairs of a decoded list (0 past its end)
    res = np.zeros(n, dtype=np.uint8)
    for k in range(min(n, 4 * len(data))):
        res[k] = (data[k // 4] >> (2 * (k % 4))) & 3
    return res


def write_cpvs(path, sets):
    # sets: for each PSDL room (in the order of the PSDL, from room 1), the boolean array of the visible rooms (index 0
    # = room 1)
    lists = []
    for visible in sets:
        lists.append(encode_list(np.concatenate(([False], np.asarray(visible, dtype=bool)))))
    file = BinaryFileHelper(path, 'wb')
    try:
        file.write_raw_string(HEADER)
        file.write_uint32(len(sets) + 2)
        offset = 0
        for data in lists:
            file.write_uint32(offset)
            offset += len(data)
        file.write_uint32(offset)
        for data in lists:
            file.file.write(data)
    finally:
        file.file.close()


def read_cpvs(path):
    # the decoded lists of a CPVS file and the number of rooms
    with open(path, 'rb') as f:
        b = f.read()
    if b[:4] != HEADER.encode('ascii'):
        raise Exception(path + " is not a CPVS file")
    n_rooms = int(np.frombuffer(b, dtype='<u4', count=1, offset=4)[0]) - 2
    offsets = np.frombuffer(b, dtype='<u4', count=n_rooms + 1, offset=8).astype(int)
    base = 8 + 4 * (n_rooms + 1)
    if base + offsets[-1] != len(b):
        raise Exception(path + ": the end offset doesn't match the size of the file")
    return n_rooms, [decode_list(b[base + offsets[i]:base + offsets[i + 1]]) for i in range(n_rooms)]


# --- the visibility


def sample_triangles(tris, spacing):
    # points on the triangles (t, 3, 3), at most about spacing apart (horizontally), with the index of their triangle;
    # yields them in groups (of triangles of the same subdivision)
    if len(tris) == 0:
        return
    edges = np.stack([tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 1], tris[:, 0] - tris[:, 2]], axis=1)
    longest = np.max(np.linalg.norm(edges[:, :, :2], axis=2), axis=1)
    subdivisions = np.clip(np.ceil(longest / spacing), 1, 512).astype(int)
    for n in np.unique(subdivisions):
        index = np.flatnonzero(subdivisions == n)
        i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing='ij')
        keep = i + j <= n
        u = (i[keep] / n)[None, :, None]
        v = (j[keep] / n)[None, :, None]
        for start in range(0, len(index), max(1, 200000 // u.shape[1])):
            group = index[start:start + max(1, 200000 // u.shape[1])]
            t = tris[group]
            points = t[:, None, 0] + u * (t[:, None, 1] - t[:, None, 0]) + v * (t[:, None, 2] - t[:, None, 0])
            yield points.reshape(-1, 3), np.repeat(group, u.shape[1])


def sample_edges(tris, spacing):
    # points along the edges of the triangles (t, 3, 3), at most spacing apart (horizontally); yields them in groups
    if len(tris) == 0:
        return
    starts = tris.reshape(-1, 3)
    ends = tris[:, [1, 2, 0]].reshape(-1, 3)
    lengths = np.linalg.norm((ends - starts)[:, :2], axis=1)
    subdivisions = np.clip(np.ceil(lengths / spacing), 1, 4096).astype(int)
    for n in np.unique(subdivisions):
        index = np.flatnonzero(subdivisions == n)
        t = (np.arange(n + 1) / n)[None, :, None]
        for start in range(0, len(index), max(1, 200000 // (n + 1))):
            group = index[start:start + max(1, 200000 // (n + 1))]
            a, b = starts[group][:, None], ends[group][:, None]
            yield (a + t * (b - a)).reshape(-1, 3)


class CPVSGenerator:
    # The visible sets from plain arrays (z up):
    # - floors: for each room, the triangles (t, 3, 3) of its floor (where the cars, so the camera, go); the viewpoints
    #   are on them, and they open the passages under the occluders (see rasterize_occluders)
    # - targets: for each room, triangles (t, 3, 3) of what is drawn with the room (its surfaces, facades, the boxes of
    #   its objects): the room is visible if one of their points is
    # - occluders: triangles (t, 3, 3) and their kind (OCCLUDER_GROUND, OCCLUDER_CLOSED)
    # - neighbours: for each room, the rooms always visible from it (besides itself)
    def __init__(self, floors, targets, occluders, occluder_kinds, neighbours, parameters, progress=None):
        self.n_rooms = len(floors)
        self.floors = [np.asarray(f, dtype=float).reshape(-1, 3, 3) for f in floors]
        self.targets = [np.asarray(t, dtype=float).reshape(-1, 3, 3) for t in targets]
        self.occluders = np.asarray(occluders, dtype=float).reshape(-1, 3, 3)
        self.occluder_kinds = np.asarray(occluder_kinds, dtype=int).reshape(-1)
        self.neighbours = neighbours
        self.p = parameters
        self.progress = progress

    def setup_grid(self):
        points = [t.reshape(-1, 3) for t in self.floors + self.targets if len(t) > 0]
        if len(self.occluders) > 0:
            points.append(self.occluders.reshape(-1, 3))
        points = np.concatenate(points) if points else np.zeros((1, 3))
        lo = points[:, :2].min(axis=0) - 1.0
        hi = points[:, :2].max(axis=0) + 1.0
        self.cell = max(self.p.cell, float(np.max(hi - lo)) / self.p.max_cells)
        self.origin = lo
        self.shape = tuple(int(c) for c in np.maximum(np.ceil((hi - lo) / self.cell), 1).astype(int)[::-1])  # (y, x)
        self.extent = float(np.linalg.norm(hi - lo))

    def cell_index(self, points):
        ix = np.floor((points[:, 0] - self.origin[0]) / self.cell).astype(int)
        iy = np.floor((points[:, 1] - self.origin[1]) / self.cell).astype(int)
        return np.clip(iy, 0, self.shape[0] - 1) * self.shape[1] + np.clip(ix, 0, self.shape[1] - 1)

    def cell_centres(self, tris):
        # the cells whose centre is inside a triangle (horizontally), with the height of the triangle there; yields
        # them in groups. The vertical triangles have none
        if len(tris) == 0:
            return
        a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
        det = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])
        keep = np.abs(det) > 1e-9
        lo = np.floor((tris[:, :, :2].min(axis=1) - self.origin) / self.cell - 0.5).astype(int) + 1
        hi = np.floor((tris[:, :, :2].max(axis=1) - self.origin) / self.cell - 0.5).astype(int)
        size = np.max(hi - lo + 1, axis=1)
        keep &= size > 0
        for m in np.unique(size[keep]):
            index = np.flatnonzero(keep & (size == m))
            gx, gy = np.meshgrid(np.arange(m), np.arange(m), indexing='ij')
            gx, gy = gx.reshape(-1), gy.reshape(-1)
            for start in range(0, len(index), max(1, 200000 // len(gx))):
                group = index[start:start + max(1, 200000 // len(gx))]
                ix = lo[group, 0, None] + gx[None, :]
                iy = lo[group, 1, None] + gy[None, :]
                px = self.origin[0] + (ix + 0.5) * self.cell
                py = self.origin[1] + (iy + 0.5) * self.cell
                ta, tb, tc = a[group], b[group], c[group]
                d = det[group, None]
                u = ((px - ta[:, 0, None]) * (tc[:, 1, None] - ta[:, 1, None]) - (tc[:, 0, None] - ta[:, 0, None]) * (py - ta[:, 1, None])) / d
                v = ((tb[:, 0, None] - ta[:, 0, None]) * (py - ta[:, 1, None]) - (px - ta[:, 0, None]) * (tb[:, 1, None] - ta[:, 1, None])) / d
                inside = (u >= 0) & (v >= 0) & (u + v <= 1) & (ix <= hi[group, 0, None]) & (iy <= hi[group, 1, None]) & \
                         (ix >= 0) & (iy >= 0) & (ix < self.shape[1]) & (iy < self.shape[0])
                z = ta[:, 2, None] + u * (tb[:, 2, None] - ta[:, 2, None]) + v * (tc[:, 2, None] - ta[:, 2, None])
                yield (iy * self.shape[1] + ix)[inside], z[inside]

    def rasterize_occluders(self):
        # self.top: the highest occluder of each cell (-inf without occluders). Below the ground and the walls all is
        # taken as solid (the height field), except in the passages: the cells whose centre has a floor lower than a
        # ground occluder over it by more than the clearance (under a bridge, an overpass, terrain over a tunnel) have
        # no occluder. The floors and the ground are compared at the same points (the centres of the cells), so that
        # the edges of a higher floor (a raised block next to a street) are not passages
        size = self.shape[0] * self.shape[1]
        top = np.full(size, -np.inf)
        spacing = 0.5 * self.cell
        tris = self.occluders
        ground = np.full(size, -np.inf)
        if len(tris) > 0:
            # the top of the cells: the walls (steep triangles) sampled densely, the other triangles at the centres of
            # the cells and along their edges
            normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
            steep = np.abs(normals[:, 2]) < 0.5 * np.linalg.norm(normals, axis=1)
            for points, _ in sample_triangles(tris[steep], spacing):
                np.maximum.at(top, self.cell_index(points), points[:, 2])
            for points in sample_edges(tris[~steep], spacing):
                np.maximum.at(top, self.cell_index(points), points[:, 2])
            for cells, z in self.cell_centres(tris[~steep]):
                np.maximum.at(top, cells, z)
            for cells, z in self.cell_centres(tris[self.occluder_kinds == OCCLUDER_GROUND]):
                np.maximum.at(ground, cells, z)
        floor = np.full(size, np.inf)
        for tris in self.floors:
            for cells, z in self.cell_centres(tris):
                np.minimum.at(floor, cells, z)
        passage = (floor < ground - self.p.clearance).reshape(self.shape)
        # the edges of the occluder over a passage are in the cells around it
        padded = np.pad(passage, 1)
        grown = passage.copy()
        for dy in (0, 1, 2):
            for dx in (0, 1, 2):
                grown |= padded[dy:dy + self.shape[0], dx:dx + self.shape[1]]
        passage = grown.reshape(-1)
        top[passage] = -np.inf
        self.top = top
        self.passages = int(np.count_nonzero(passage))

    def setup_targets(self):
        # the targets: the highest point of each room in each target cell (if a lower point of a column is visible, the
        # higher one is too)
        cell = max(self.p.target_cell, self.cell)
        xs, ys, zs, rooms, tiles = [], [], [], [], []
        for r in range(self.n_rooms):
            tris = self.targets[r]
            if len(tris) == 0:
                continue
            pts = [t for t, _ in sample_triangles(tris, cell)] + [tris.reshape(-1, 3)]
            pts = np.concatenate(pts)
            keys = np.floor((pts[:, :2] - self.origin) / cell).astype(np.int64)
            key = keys[:, 1] * 1000003 + keys[:, 0]
            order = np.lexsort((-pts[:, 2], key))
            key = key[order]
            first = np.ones(len(key), dtype=bool)
            first[1:] = key[1:] != key[:-1]
            sel = order[first]
            centre = (np.floor((pts[sel, :2] - self.origin) / cell) + 0.5) * cell + self.origin
            # in groups by tile (contiguous), so that the far parts of a large room are left out on their own
            tile = np.floor((centre - self.origin) / TARGET_TILE).astype(np.int64)
            order = np.argsort(tile[:, 1] * 1000003 + tile[:, 0], kind='stable')
            xs.append(centre[order, 0])
            ys.append(centre[order, 1])
            zs.append(pts[sel, 2][order])
            rooms.append(np.full(len(sel), r))
            tiles.append((tile[order, 1] * 1000003 + tile[order, 0]) * self.n_rooms + r)
        if xs:
            self.tx, self.ty, self.tz = np.concatenate(xs), np.concatenate(ys), np.concatenate(zs)
            self.troom = np.concatenate(rooms)
            tiles = np.concatenate(tiles)
        else:
            self.tx = self.ty = self.tz = np.zeros(0)
            self.troom = np.zeros(0, dtype=int)
            tiles = np.zeros(0, dtype=np.int64)
        self.max_target_z = float(self.tz.max()) if len(self.tz) > 0 else 0.0
        # the groups of targets (a room in a tile, contiguous), with the circle (horizontally) and the highest point
        # around them
        first = np.ones(len(tiles), dtype=bool)
        first[1:] = tiles[1:] != tiles[:-1]
        self.gstart = np.flatnonzero(first)
        self.gend = np.append(self.gstart[1:], len(tiles))
        self.groom = self.troom[self.gstart]
        n = len(self.gstart)
        self.gx, self.gy, self.gradius, self.gz = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
        if n > 0:
            self.gx = 0.5 * (np.minimum.reduceat(self.tx, self.gstart) + np.maximum.reduceat(self.tx, self.gstart))
            self.gy = 0.5 * (np.minimum.reduceat(self.ty, self.gstart) + np.maximum.reduceat(self.ty, self.gstart))
            group = np.repeat(np.arange(n), self.gend - self.gstart)
            self.gradius = np.maximum.reduceat(np.hypot(self.tx - self.gx[group], self.ty - self.gy[group]), self.gstart) + 0.75 * cell
            self.gz = np.maximum.reduceat(self.tz, self.gstart)

    def viewpoints(self, r):
        # the viewpoints of a room: points of its floor (the centres of its triangles, then their vertices), the first
        # near its middle, the next ones each the farthest from those before (until max_viewpoints, or closer than
        # viewpoint_spacing)
        tris = self.floors[r]
        if len(tris) == 0:
            tris = self.targets[r]
        if len(tris) == 0:
            return np.zeros((0, 3))
        candidates = np.concatenate([tris.mean(axis=1), tris.reshape(-1, 3)])
        area = 0.5 * np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1)
        middle = (tris.mean(axis=1) * area[:, None]).sum(axis=0) / max(area.sum(), 1e-12) if area.sum() > 1e-9 else candidates.mean(axis=0)
        n_centres = len(tris)
        # the points in a cell of an occluder (next to a wall) only if the room has no others
        free = self.top[self.cell_index(candidates)] <= candidates[:, 2] + min(self.p.eye_heights)
        if np.any(free):
            n_centres = int(np.count_nonzero(free[:n_centres]))
            candidates = np.concatenate([candidates[:len(tris)][free[:len(tris)]], candidates[len(tris):][free[len(tris):]]])
            if n_centres == 0:
                n_centres = len(candidates)
        chosen = [int(np.argmin(np.linalg.norm(candidates[:n_centres, :2] - middle[:2], axis=1)))]
        distance = np.linalg.norm(candidates[:, :2] - candidates[chosen[0], :2], axis=1)
        while len(chosen) < self.p.max_viewpoints:
            far = int(np.argmax(distance))
            if distance[far] < self.p.viewpoint_spacing:
                break
            chosen.append(far)
            distance = np.minimum(distance, np.linalg.norm(candidates[:, :2] - candidates[far, :2], axis=1))
        return candidates[chosen]

    def setup_rays(self):
        # the steps along the rays: one cell apart up to NEAR_STEPS cells, then twice as long (on a grid of cells twice
        # as large, each the lowest of the four below it, so that it hides only what they all hide) every time the
        # distance doubles
        a = np.arange(self.p.azimuths) * (2 * math.pi / self.p.azimuths)
        self.cos = np.cos(a)
        self.sin = np.sin(a)
        distances, levels = [], []
        d, level = 0.0, 0
        while d < self.extent + self.cell:
            step = self.cell * 2 ** level
            d += step
            distances.append(d)
            levels.append(level)
            if d >= NEAR_STEPS * self.cell * 2 ** level - 1e-6:
                level += 1
        self.distances = np.array(distances)
        self.n_steps = len(distances)
        self.segments = []  # (first step, end step, level), at most CHUNK steps each
        levels = np.array(levels)
        for level in np.unique(levels):
            steps = np.flatnonzero(levels == level)
            for s0 in range(steps[0], steps[-1] + 1, CHUNK):
                self.segments.append((s0, min(s0 + CHUNK, steps[-1] + 1), int(level)))
        self.grids = [self.top.reshape(self.shape)]
        for level in range(1, int(levels.max()) + 1):
            g = self.grids[-1]
            g = np.pad(g, ((0, g.shape[0] % 2), (0, g.shape[1] % 2)), constant_values=-np.inf)
            self.grids.append(np.minimum(np.minimum(g[0::2, 0::2], g[1::2, 0::2]), np.minimum(g[0::2, 1::2], g[1::2, 1::2])))
        self.horizon = np.empty((self.p.azimuths, self.n_steps), dtype=np.float64)
        self.ends = np.zeros(self.p.azimuths, dtype=int)

    def steps_before(self, d):
        # the last step of the rays before a target at the distance d: the occluders in its cell and the one before
        # don't hide it (-1: none)
        return np.searchsorted(self.distances, d, side='right') - 3

    def cast(self, ex, ey, ez, inside):
        # self.horizon[a, s]: the highest elevation (dz / distance) of the occluders along the ray a up to the step s,
        # valid up to self.ends[a] (past it the ray is blocked for every target, or out of the city: the last value).
        # From an eye inside an occluder (a floor under a roof, or a cell of a wall), the occluders the rays start in
        # (the first cells above the eye) are left out: the room is seen as from the edge of the building
        A = self.p.azimuths
        carry = np.full(A, -np.inf)
        starting = np.full(A, inside)
        active = np.arange(A)
        self.ends[:] = 0
        for s0, s1, level in self.segments:
            if len(active) == 0:
                break
            grid = self.grids[level]
            height, width = grid.shape
            cell = self.cell * 2 ** level
            d = self.distances[s0:s1]
            xs = ex + self.cos[active, None] * d
            ys = ey + self.sin[active, None] * d
            ix = np.floor((xs - self.origin[0]) / cell).astype(int)
            iy = np.floor((ys - self.origin[1]) / cell).astype(int)
            inside = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
            heights = np.where(inside, grid.reshape(-1)[np.clip(iy, 0, height - 1) * width + np.clip(ix, 0, width - 1)], -np.inf)
            if np.any(starting[active]):
                start = np.logical_and.accumulate(heights > ez, axis=1) & starting[active, None]
                heights[start] = -np.inf
                starting[active] = start[:, -1]
            elevation = (heights - ez) / d
            elevation[:, 0] = np.maximum(elevation[:, 0], carry[active])
            elevation = np.maximum.accumulate(elevation, axis=1)
            self.horizon[active, s0:s1] = elevation
            carry[active] = elevation[:, -1]
            self.ends[active] = s1
            # the rays stop when no target can be above their horizon any more, or when they left the city
            next_d = self.distances[s1] if s1 < self.n_steps else np.inf
            threshold = (self.max_target_z - ez) / next_d if self.max_target_z > ez else 0.0
            out = ~inside[:, -1]
            active = active[(carry[active] <= threshold) & ~out]

    def visible_targets(self, ex, ey, ez, candidates):
        # which of the candidate targets are above the horizon of the last cast
        dx = self.tx[candidates] - ex
        dy = self.ty[candidates] - ey
        d = np.maximum(np.hypot(dx, dy), 1e-6)
        f = np.mod(np.arctan2(dy, dx), 2 * math.pi) * (self.p.azimuths / (2 * math.pi))
        k0 = np.floor(f).astype(int) % self.p.azimuths
        k1 = (k0 + 1) % self.p.azimuths
        s = self.steps_before(d)
        near = s < 0
        s = np.maximum(s, 0)
        h0 = self.horizon[k0, np.minimum(s, self.ends[k0] - 1)]
        h1 = self.horizon[k1, np.minimum(s, self.ends[k1] - 1)]
        elevation = (self.tz[candidates] - ez) / d
        return near | (elevation >= np.minimum(h0, h1))

    def possibly_visible(self, ex, ey, ez, groups):
        # which of the groups of targets may have a visible target after the last cast: a group is left out when its
        # highest target, at the nearest distance of its circle, is below the lowest horizon of the rays across the
        # circle (the horizon only grows along a ray, so none of its targets can be above it)
        A = self.p.azimuths
        dx = self.gx[groups] - ex
        dy = self.gy[groups] - ey
        d = np.hypot(dx, dy)
        radius = self.gradius[groups]
        near = d - radius
        s = self.steps_before(near)
        res = (s < 0) | (radius * 1.05 >= d)
        far = np.flatnonzero(~res)
        if len(far) == 0:
            return res
        dz = self.gz[groups[far]] - ez
        bound = np.where(dz > 0, dz / near[far], dz / (d[far] + radius[far]))
        half = np.arcsin(np.minimum(radius[far] / d[far], 1.0))
        angle = np.arctan2(dy[far], dx[far])
        k0 = np.floor((angle - half) * (A / (2 * math.pi))).astype(int)
        k1 = np.floor((angle + half) * (A / (2 * math.pi))).astype(int) + 1
        counts = np.minimum(k1 - k0 + 1, A)
        offsets = np.repeat(np.cumsum(counts) - counts, counts)
        k = (np.repeat(k0, counts) + np.arange(int(counts.sum())) - offsets) % A
        steps = np.minimum(np.repeat(s[far], counts), self.ends[k] - 1)
        lowest = np.minimum.reduceat(self.horizon[k, steps], np.cumsum(counts) - counts)
        res[far] = bound >= lowest
        return res

    def eye(self, point, height):
        # the eye above a floor point, and whether it is inside an occluder (under a roof, in a cell of a wall)
        z = point[2] + height
        return z, bool(self.top[self.cell_index(point[None, :])[0]] > z)

    def generate(self, sources=None):
        # the visible sets: for each room (or each of the sources), a boolean array over the rooms
        self.setup_grid()
        self.rasterize_occluders()
        self.setup_targets()
        self.setup_rays()
        res = []
        sources = range(self.n_rooms) if sources is None else sources
        step = max(1, len(sources) // 10)
        for i, r in enumerate(sources):
            if self.progress is not None and i % step == 0:
                self.progress(i, len(sources))
            visible = np.zeros(self.n_rooms, dtype=bool)
            visible[r] = True
            for n in self.neighbours[r]:
                visible[n] = True
            for point in self.viewpoints(r):
                for height in self.p.eye_heights:
                    groups = np.flatnonzero(~visible[self.groom])
                    if len(groups) == 0:
                        break
                    ez, inside = self.eye(point, height)
                    self.cast(point[0], point[1], ez, inside)
                    groups = groups[self.possibly_visible(point[0], point[1], ez, groups)]
                    if len(groups) == 0:
                        continue
                    counts = self.gend[groups] - self.gstart[groups]
                    candidates = np.repeat(self.gstart[groups] - (np.cumsum(counts) - counts), counts) + np.arange(int(counts.sum()))
                    seen = candidates[self.visible_targets(point[0], point[1], ez, candidates)]
                    visible[self.troom[seen]] = True
            res.append(visible)
        return res


def shared_vertex_neighbours(room_points, tolerance=0.05):
    # the rooms sharing a point (within the tolerance) with each room
    keys = {}
    for r, pts in enumerate(room_points):
        for key in set(map(tuple, np.round(np.asarray(pts).reshape(-1, 3) / tolerance).astype(np.int64).tolist())):
            keys.setdefault(key, set()).add(r)
    res = [set() for _ in room_points]
    for rooms in keys.values():
        if len(rooms) > 1:
            for r in rooms:
                res[r].update(rooms)
    for r in range(len(res)):
        res[r].discard(r)
    return res


# --- the scene of the exporter

# the parts on which the cars go (the viewpoints are on them), the ones taken as walls or ground for the occlusion and
# the closed ones (roofs). The facades (FAC, SLIVER) are covered by their bounds (FACB), the tunnels (RAIL) are made by
# the game
FLOOR_TYPES = {"ROADS", "ROADSN", "ROADN", "ROADD", "ROADDN", "SW", "CW", "IS", "BLOCK", "NUL"}
GROUND_OCCLUDER_TYPES = {"ROADS", "ROADSN", "ROADN", "ROADD", "ROADDN", "SW", "CW", "IS", "BLOCK", "FACB"}
CLOSED_OCCLUDER_TYPES = {"ROOF"}
MIN_FLOOR_NORMAL = 0.5  # the floors steeper than this (the z of their normal) are left out


def part_triangles(part):
    vertices = np.asarray(part.vertices, dtype=float).reshape(-1, 3)
    if len(vertices) == 0:
        return np.zeros((0, 3, 3))
    indices = part.indices
    if part.is_mesh:
        indices = [i for s in part.submeshes for i in s]
    indices = np.asarray(indices, dtype=int)
    indices = indices[:len(indices) // 3 * 3]
    if len(indices) == 0 or indices.max() >= len(vertices):
        return np.zeros((0, 3, 3))
    return vertices[indices].reshape(-1, 3, 3)


def flat_triangles(tris):
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    return tris[(lengths > 1e-9) & (np.abs(normals[:, 2]) >= MIN_FLOOR_NORMAL * np.maximum(lengths, 1e-12))]


def instance_box_top(part):
    # the top face of the box of a mesh instance (from its bounds property, local to the mesh in the space of the
    # program) placed in the city, as two triangles at the height of the highest corner
    bounds = part.properties.get('bounds')
    if not bounds:
        return np.zeros((0, 3, 3))
    values = [float(v) for v in str(bounds).split(',')]
    lo, hi = values[:3], values[3:6]
    matrix = part.transform_matrix()
    corners = []
    for x in (lo[0], hi[0]):
        for y in (lo[1], hi[1]):
            for z in (lo[2], hi[2]):
                v = to_writer_space((x, y, z))
                corners.append(np.dot(matrix, (v[0], v[1], v[2], 1))[:3])
    corners = np.array(corners)
    # the corners of the face at the local top (y of the program): indices with y = hi
    face = corners[[2, 3, 7, 6]].copy()
    face[:, 2] = corners[:, 2].max()
    return np.array([[face[0], face[1], face[2]], [face[0], face[2], face[3]]])


class CPVSWriter:
    def __init__(self, scene: Scene, psdl_path, accurate):
        self.scene = scene
        self.path = psdl_path[:-len('.psdl')] + '.cpvs' if psdl_path.lower().endswith('.psdl') else psdl_path + '.cpvs'
        self.parameters = ACCURATE if accurate else FAST

    def inputs(self):
        n = len(self.scene.blocks)
        floors = [[] for _ in range(n)]
        targets = [[] for _ in range(n)]
        points = [[] for _ in range(n)]
        occluders = []
        kinds = []
        for part in self.scene.parts:
            r = self.scene.block_index(part.block)
            if r < 0:
                continue
            if part.type == "INST":
                targets[r].append(instance_box_top(part))
                continue
            if part.type not in ("PKG",) and not is_surface(part):
                continue
            tris = part_triangles(part)
            if len(tris) == 0:
                continue
            targets[r].append(tris)
            if part.type == "PKG":
                continue
            points[r].append(tris.reshape(-1, 3))
            if part.type in FLOOR_TYPES:
                floors[r].append(flat_triangles(tris))
            if part.type in GROUND_OCCLUDER_TYPES:
                occluders.append(tris)
                kinds.append(np.full(len(tris), OCCLUDER_GROUND))
            elif part.type in CLOSED_OCCLUDER_TYPES:
                occluders.append(tris)
                kinds.append(np.full(len(tris), OCCLUDER_CLOSED))

        def joined(lst):
            return np.concatenate(lst) if lst else np.zeros((0, 3, 3))

        neighbours = shared_vertex_neighbours([np.concatenate(p) if p else np.zeros((0, 3)) for p in points])
        return ([joined(f) for f in floors], [joined(t) for t in targets], joined(occluders),
                np.concatenate(kinds) if kinds else np.zeros(0, dtype=int), neighbours)

    def write(self):
        floors, targets, occluders, kinds, neighbours = self.inputs()

        def progress(r, n):
            print("computing the CPVS: room " + str(r + 1) + " of " + str(n))

        generator = CPVSGenerator(floors, targets, occluders, kinds, neighbours, self.parameters, progress)
        sets = generator.generate()
        write_cpvs(self.path, sets)
        if len(sets) > 0:
            counts = [int(np.count_nonzero(s)) for s in sets]
            print("CPVS: " + str(len(sets)) + " rooms, " + str(round(float(np.mean(counts)), 1)) + " visible from each on average (max "
                  + str(max(counts)) + ")")
