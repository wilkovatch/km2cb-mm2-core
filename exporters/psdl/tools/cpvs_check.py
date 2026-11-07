# Checks CPVS files (stock or exported), compares them, and computes the CPVS of a PSDL with the generator of the
# exporter (writers/cpvs_writer.py) to compare it with the stock one
#
#   python -I cpvs_check.py file.cpvs file.psdl
#       the layout (the number of rooms, the offsets, the lengths of the lists, the reserved pairs, the values), how many
#       rooms see themselves and their perimeter neighbours, and how many rooms each one sees
#   python -I cpvs_check.py --compare a.cpvs b.cpvs
#       how many of the visible pairs of b are visible in a (the recall of a), and how many rooms each one sees
#   python -I cpvs_check.py --stock file.psdl [--accurate] [--out x.cpvs]
#       computes the CPVS of the PSDL from its floors (roads, sidewalks, fans), facade bounds and roofs (the PSDL has
#       no objects), and compares it with the .cpvs next to it (the stock london.cpvs and sf.cpvs)
# Exits with 1 if something is wrong in the checked file.

import os
import struct
import sys
import time

import numpy as np

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [TOOLS, os.path.dirname(TOOLS)]
from psdl_check import Reader  # noqa: E402
from writers.cpvs_writer import (CPVSGenerator, FAST, ACCURATE, OCCLUDER_GROUND, OCCLUDER_CLOSED, read_cpvs,  # noqa: E402
                                 list_values, write_cpvs)


def read_psdl_geometry(path):
    # vertices (z up), heights, and for each room its perimeter (vertex, neighbour) pairs and its attribute words
    r = Reader(path)
    if r.b[:4] != b'PSD0':
        raise Exception(path + ' is not a PSDL file')
    r.o = 8
    n_vertices = r.u32()
    v = np.frombuffer(r.b, dtype='<f4', count=3 * n_vertices, offset=r.o).astype(float).reshape(-1, 3)
    r.skip(12 * n_vertices)
    n_heights = r.u32()
    heights = np.frombuffer(r.b, dtype='<f4', count=n_heights, offset=r.o).astype(float)
    r.skip(4 * n_heights)
    for _ in range(r.u32() - 1):
        r.skip(r.unpack('B')[0])
    n_rooms = r.u32() - 1
    r.u32()
    rooms = []
    for _ in range(n_rooms):
        n_points, n_attributes = r.unpack('2I')
        pairs = np.frombuffer(r.b, dtype='<u2', count=2 * n_points, offset=r.o).tolist()
        r.skip(4 * n_points)
        rooms.append((list(zip(pairs[0::2], pairs[1::2])), list(r.unpack(str(n_attributes) + 'H'))))
    return v[:, [0, 2, 1]], heights, rooms


def strip_triangles(sections):
    # the triangles between consecutive sections of a strip (each section a list of points across it)
    res = []
    for a, b in zip(sections[:-1], sections[1:]):
        for j in range(len(a) - 1):
            res.append((a[j], a[j + 1], b[j + 1]))
            res.append((a[j], b[j + 1], b[j]))
    return res


def fan_triangles(points):
    return [(points[0], points[k], points[k + 1]) for k in range(1, len(points) - 1)]


def room_geometry(vertices, heights, words):
    # the floors, walls (facade bounds), roofs and other drawn surfaces (facades, slivers) of the attributes of a room
    floors, walls, roofs, others = [], [], [], []

    def vtx(i):
        return vertices[i]

    def raised(i, z):
        p = vertices[i].copy()
        p[2] = z
        return p

    i = 0
    while i < len(words):
        word = words[i]
        i += 1
        typ = (word >> 3) & 15
        subtype = word & 7
        if typ in (0, 1, 2, 4, 5, 6, 8, 9, 12):
            n = subtype
            if subtype == 0:
                n = words[i]
                i += 1
            if typ in (0, 1, 2):
                k = {0: 4, 1: 2, 2: 2}[typ]
                refs = words[i:i + k * n]
                floors += strip_triangles([[vtx(refs[s * k + j]) for j in range(k)] for s in range(n)])
                i += k * n
            elif typ == 8:
                refs = words[i + 2:i + 2 + 6 * n]
                floors += strip_triangles([[vtx(refs[s * 6 + j]) for j in range(6)] for s in range(n)])
                i += 2 + 6 * n
            elif typ in (5, 6):
                floors += fan_triangles([vtx(j) for j in words[i:i + n + 2]])
                i += n + 2
            elif typ == 12:
                z = heights[words[i]]
                roofs += fan_triangles([raised(j, z) for j in words[i + 1:i + n + 2]])
                i += n + 2
            elif typ == 4:  # crosswalk: 4 vertices
                refs = words[i:i + n]
                if len(refs) == 4:
                    floors += strip_triangles([[vtx(refs[0]), vtx(refs[1])], [vtx(refs[2]), vtx(refs[3])]])
                i += n
            else:  # tunnel
                i += n
        elif typ == 7:  # facade bound: angle, top, left, right
            top, a, b = heights[words[i + 1]], words[i + 2], words[i + 3]
            walls += [(vtx(a), vtx(b), raised(b, top)), (vtx(a), raised(b, top), raised(a, top))]
            i += 4
        elif typ == 3:  # sliver: top, texture scale, left, right
            top, a, b = heights[words[i]], words[i + 2], words[i + 3]
            others += [(vtx(a), vtx(b), raised(b, top)), (vtx(a), raised(b, top), raised(a, top))]
            i += 4
        elif typ == 11:  # facade: bottom, top, u, v, left, right
            bottom, top, a, b = heights[words[i]], heights[words[i + 1]], words[i + 4], words[i + 5]
            others += [(raised(a, bottom), raised(b, bottom), raised(b, top)), (raised(a, bottom), raised(b, top), raised(a, top))]
            i += 6
        elif typ == 10:
            i += 1
        else:
            break
        if word & 0x80:
            break

    def arr(lst):
        return np.array(lst, dtype=float).reshape(-1, 3, 3)

    return arr(floors), arr(walls), arr(roofs), arr(others)


def read_inst(path):
    # the records of an INST file: (room index from 0, object name, origin, x, y and z axes), in the space of the game
    b = open(path, 'rb').read()
    o = 0
    res = []
    while o < len(b):
        room, _, typ = struct.unpack_from('<HHB', b, o)
        o += 5
        n = typ & 0x7f
        name = b[o:o + n].split(b'\0')[0].decode('latin-1')
        o += n
        if typ & 0x80:  # the x axis (x and z), y up
            dx, dz = struct.unpack_from('<ff', b, o)
            origin = np.array(struct.unpack_from('<3f', b, o + 8))
            o += 20
            axes = np.array([[dx, 0, dz], [0, 1, 0], [-dz, 0, dx]])
        else:
            values = struct.unpack_from('<12f', b, o)
            o += 48
            axes = np.array(values[:9]).reshape(3, 3)
            origin = np.array(values[9:])
        res.append((room - 1, name, origin, axes))
    return res


def pkg_bounds(path):
    # the box of the vertices of the meshes of a PKG file (the reader of the core's server), None if unreadable
    sys.path.insert(0, os.path.join(TOOLS, '..', '..', '..', 'server'))
    import mesh_formats
    try:
        size = os.path.getsize(path)
        f = mesh_formats.BinaryFileHelper(path, 'rb')
        materials, objects = [], []
        header = f.read_bytes(4)
        if header not in (b'PKG2', b'PKG3'):
            return None
        while not mesh_formats.reached_end(f, size):
            mesh_formats.read_pkg_file(f, header, materials, objects)
        f.close()
        points = np.array([v for obj in objects for v in obj['vertices']], dtype=float).reshape(-1, 3)
        return (points.min(axis=0), points.max(axis=0)) if len(points) else None
    except Exception:
        return None


def instance_tops(inst_path, geometry_dir, n_rooms):
    # for each room, the top faces of the boxes of its objects (z up), as targets
    res = [[] for _ in range(n_rooms)]
    bounds = {}
    missing = set()
    for room, name, origin, axes in read_inst(inst_path):
        if not 0 <= room < n_rooms:
            continue
        key = name.lower()
        if key not in bounds:
            path = os.path.join(geometry_dir, name + '.pkg')
            bounds[key] = pkg_bounds(path) if os.path.exists(path) else None
            if bounds[key] is None:
                missing.add(name)
        if bounds[key] is None:
            continue
        lo, hi = bounds[key]
        corners = np.array([origin + x * axes[0] + y * axes[1] + z * axes[2]
                            for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])[:, [0, 2, 1]]
        face = corners[[2, 3, 7, 6]].copy()
        face[:, 2] = corners[:, 2].max()
        res[room] += [[face[0], face[1], face[2]], [face[0], face[2], face[3]]]
    if missing:
        print("%d objects without a readable PKG (left out), e.g. %s" % (len(missing), sorted(missing)[:3]))
    return [np.array(r, dtype=float).reshape(-1, 3, 3) for r in res]


def stock_inputs(path, with_objects=True):
    # the inputs of the generator from a PSDL; with_objects: also the objects of the INST next to it (the boxes of the
    # PKG files of the geometry folder next to the city folder, as the stock files are laid out)
    vertices, heights, rooms = read_psdl_geometry(path)
    floors, targets, occluders, kinds, neighbours = [], [], [], [], []
    for perimeter, words in rooms:
        f, w, roof, other = room_geometry(vertices, heights, words)
        if len(f) == 0 and len(perimeter) >= 3:
            # no floor attributes: the perimeter as a fan
            f = np.array(fan_triangles([vertices[p] for p, _ in perimeter]), dtype=float).reshape(-1, 3, 3)
        floors.append(f)
        targets.append(np.concatenate([f, w, roof, other]))
        occluders += [f, w, roof]
        kinds += [np.full(len(f) + len(w), OCCLUDER_GROUND), np.full(len(roof), OCCLUDER_CLOSED)]
        neighbours.append({q - 1 for _, q in perimeter if q > 0})
    inst = os.path.splitext(path)[0] + '.inst'
    geometry = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(path))), 'geometry')
    if with_objects and os.path.exists(inst) and os.path.isdir(geometry):
        for r, tops in enumerate(instance_tops(inst, geometry, len(rooms))):
            targets[r] = np.concatenate([targets[r], tops])
    return floors, targets, np.concatenate(occluders), np.concatenate(kinds), neighbours


def matrix(n_rooms, lists):
    # visible[i, j]: room j + 1 visible from room i + 1
    return np.array([list_values(data, n_rooms + 1)[1:] == 3 for data in lists]).reshape(n_rooms, n_rooms)


def describe(name, vis):
    counts = vis.sum(axis=1) if len(vis) else np.zeros(1)
    print("%s: %d rooms, visible from each: min %d, median %d, mean %.1f, max %d (%.1f%% of the pairs)" % (
        name, len(vis), counts.min(), np.median(counts), counts.mean(), counts.max(), 100.0 * vis.mean() if vis.size else 0))


def compare(name, a, b):
    hits = np.count_nonzero(a & b)
    total = np.count_nonzero(b)
    print("%s: %.2f%% of the visible pairs of the reference are visible (%d missing), %d more visible pairs" % (
        name, 100.0 * hits / max(total, 1), total - hits, np.count_nonzero(a & ~b)))
    missing = (b & ~a).sum(axis=1)
    print("  rooms missing visible rooms: %d, the most: %d" % (np.count_nonzero(missing), missing.max() if len(missing) else 0))


def check(cpvs_path, psdl_path):
    ok = True
    vertices, heights, rooms = read_psdl_geometry(psdl_path)
    n_rooms, lists = read_cpvs(cpvs_path)
    if n_rooms != len(rooms):
        print("Error: %d rooms in the CPVS, %d in the PSDL" % (n_rooms, len(rooms)))
        return False
    full = (n_rooms + 4) // 4
    for i, data in enumerate(lists):
        if len(data) > full:
            print("Error: the list of room %d is %d bytes long (at most %d)" % (i + 1, len(data), full))
            ok = False
        values = list_values(data, n_rooms + 1)
        if values[0] != 0:
            print("Warning: the reserved pair of the list of room %d is %d" % (i + 1, values[0]))
        if np.any((values != 0) & (values != 3)):
            print("Warning: the list of room %d has values other than 0 and 3" % (i + 1))
    vis = matrix(n_rooms, lists)
    describe(os.path.basename(cpvs_path), vis)
    self_visible = int(np.count_nonzero(np.diagonal(vis))) if n_rooms else 0
    pairs = [(i, q - 1) for i, (perimeter, _) in enumerate(rooms) for _, q in perimeter if 0 < q <= n_rooms]
    seen = sum(1 for i, j in pairs if vis[i, j])
    print("self visible: %d of %d rooms, perimeter neighbours visible: %d of %d" % (self_visible, n_rooms, seen, len(pairs)))
    if self_visible < n_rooms:
        print("Warning: %d rooms don't see themselves" % (n_rooms - self_visible))
    return ok


def main(args):
    if len(args) >= 3 and args[0] == '--compare':
        na, la = read_cpvs(args[1])
        nb, lb = read_cpvs(args[2])
        if na != nb:
            print("Error: %d and %d rooms" % (na, nb))
            return 1
        a, b = matrix(na, la), matrix(nb, lb)
        describe(args[1], a)
        describe(args[2], b)
        compare(os.path.basename(args[1]), a, b)
        return 0
    if len(args) >= 2 and args[0] == '--stock':
        psdl = args[1]
        parameters = ACCURATE if '--accurate' in args else FAST
        t = time.time()
        floors, targets, occluders, kinds, neighbours = stock_inputs(psdl)
        sets = CPVSGenerator(floors, targets, occluders, kinds, neighbours, parameters,
                             lambda r, n: print("room %d of %d (%.0f s)" % (r + 1, n, time.time() - t))).generate()
        elapsed = time.time() - t
        ours = np.array(sets).reshape(len(sets), len(sets))
        print("computed in %.1f s" % elapsed)
        describe("computed", ours)
        if '--out' in args:
            write_cpvs(args[args.index('--out') + 1], sets)
        reference = os.path.splitext(psdl)[0] + '.cpvs'
        if os.path.exists(reference):
            n, lists = read_cpvs(reference)
            stock = matrix(n, lists)
            describe(os.path.basename(reference), stock)
            compare("computed", ours, stock)
        return 0
    if len(args) == 2:
        return 0 if check(args[0], args[1]) else 1
    print(__doc__ if __doc__ else "usage: cpvs_check.py file.cpvs file.psdl | --compare a.cpvs b.cpvs | --stock file.psdl [--accurate] [--out x.cpvs]")
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
