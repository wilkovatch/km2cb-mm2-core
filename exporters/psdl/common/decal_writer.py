import math
import os

import numpy as np

from .scene_input import SceneInput
from .file_io import BinaryFileHelper
from .utils import Utils
from . import report

# The decals of the city (city/<city>/decals.pathset, PTH1 like props.pathset), as the game reads them at the city load:
# - each path is one decal, with the texture named by the path (paths with less than 3 points are skipped)
# - its points, in order, are drawn as a triangle strip 1 cm above them: the even points are one side of the strip
#   (u = 0) and the odd ones the other side (u = 1)
# - v at the k-th pair of points is the distance of its even point from the first point of the path, divided by the
#   width of the first pair and rounded to an integer: the texture is tiled in square tiles as wide as the strip start
# - the decal is drawn with the room containing the middle of the points 0 and 2, when that room is visible
# - the stock decals all have ((p1 - p0) x (p2 - p0)).y > 0 (their faces point up, the other side is culled)
# - the room of the points, the type and spacing of the paths are not used (they are written as in the stock files)
# The strips are given by their centre line and width: each segment of it is a path of its own (so that the tiles
# follow the straight distance used by the game), split when it's long (so that its room stays close to all of it).
PATH_TYPE_LINE_STRIP = 2
PATH_SPACING = 20
MAX_NAME_LENGTH = 31
MAX_PATH_LENGTH = 25.0
MAX_MITER = 2.0
# the pieces with a pair further than this from a whole number of tiles are halved (at most this many times)
MAX_TILE_ERROR = 0.45
MAX_SPLITS = 3
# points closer than this to the line through their neighbours are dropped (fewer paths on resampled lines)
SIMPLIFY_TOLERANCE = 0.02
MIN_SEGMENT_LENGTH = 0.001

# the writer works in the z-up space of the scene input, the file is y-up (as BinaryFileHelper.write_vec3)
UP = np.array([0.0, 0.0, 1.0])


def to_game_space(p):
    return np.array([-p[0], p[2], p[1]], dtype=float)


def horizontal(v):
    h = np.array([v[0], v[1], 0.0], dtype=float)
    length = np.linalg.norm(h)
    return h / length if length > 1e-9 else None


def point_line_distance(p, a, b):
    ab = np.subtract(b, a)
    length2 = float(np.dot(ab, ab))
    if length2 < 1e-12:
        return float(np.linalg.norm(np.subtract(p, a)))
    t = min(max(float(np.dot(np.subtract(p, a), ab)) / length2, 0.0), 1.0)
    return float(np.linalg.norm(np.subtract(p, np.add(a, ab * t))))


def simplified(points):
    res = [np.array(points[0], dtype=float)]
    for p in points[1:]:
        p = np.array(p, dtype=float)
        if horizontal(np.subtract(p, res[-1])) is not None and np.linalg.norm(np.subtract(p, res[-1])) > MIN_SEGMENT_LENGTH:
            res.append(p)
    i = 1
    while i < len(res) - 1:
        if point_line_distance(res[i], res[i - 1], res[i + 1]) < SIMPLIFY_TOLERANCE:
            del res[i]
        else:
            i += 1
    return res


def mitered_sides(points):
    # the side direction at each point, scaled so that the sides of the segments around it keep the width
    res = []
    for i in range(len(points)):
        prev = horizontal(np.subtract(points[i], points[i - 1])) if i > 0 else None
        nxt = horizontal(np.subtract(points[i + 1], points[i])) if i < len(points) - 1 else None
        dirs = [d for d in (prev, nxt) if d is not None]
        direction = horizontal(np.sum(dirs, axis=0))
        if direction is None:
            direction = dirs[-1]
        cos = max(float(np.dot(direction, dirs[-1])), 1e-3)
        res.append(np.cross(UP, direction) * min(1.0 / cos, MAX_MITER))
    return res


def game_v(path, k):
    # the v of the k-th pair of a path (in game space), as the game computes it
    width = np.linalg.norm(np.subtract(path[0], path[1]))
    return math.floor(np.linalg.norm(np.subtract(path[2 * k], path[0])) / width + 0.5)


def path_points(a0, b0, a1, b1):
    # a straight piece of strip from the pair (a0, b0) to (a1, b1), in game space, as whole tiles;
    # returns (points, how far the pairs are from a whole number of tiles at most)
    a0, b0, a1, b1 = (to_game_space(p) for p in (a0, b0, a1, b1))
    if np.cross(np.subtract(b0, a0), np.subtract(a1, a0))[1] < 0:
        a0, b0, a1, b1 = b0, a0, b1, a1
    width = np.linalg.norm(np.subtract(a0, b0))
    if width < 1e-6:
        return None, 0.0
    tiles = np.linalg.norm(np.subtract(a1, a0)) / width
    n = max(1, int(math.floor(tiles + 0.5)))
    res = []
    for k in range(n + 1):
        t = k / n
        res.append(a0 + (a1 - a0) * t)
        res.append(b0 + (b1 - b0) * t)
    return res, abs(tiles - n)


def piece_paths(a0, b0, a1, b1, depth=0):
    # the paths of a straight piece of strip, halved while a pair is too close to the rounding of the game (where its
    # float precision could give it the v of the next tile)
    path, error = path_points(a0, b0, a1, b1)
    if path is None:
        return []
    if error > MAX_TILE_ERROR and depth < MAX_SPLITS:
        am, bm = (a0 + a1) * 0.5, (b0 + b1) * 0.5
        return piece_paths(a0, b0, am, bm, depth + 1) + piece_paths(am, bm, a1, b1, depth + 1)
    return [path]


def strip_paths(centre, width):
    # the paths of a strip along the centre line (scene space), in game space
    points = simplified(centre)
    if len(points) < 2:
        return []
    sides = [s * (width * 0.5) for s in mitered_sides(points)]
    a = [np.subtract(p, s) for p, s in zip(points, sides)]
    b = [np.add(p, s) for p, s in zip(points, sides)]
    res = []
    for i in range(len(points) - 1):
        length = float(np.linalg.norm(np.subtract(points[i + 1], points[i])))
        chunks = max(1, int(math.ceil(length / MAX_PATH_LENGTH)))
        for c in range(chunks):
            t0, t1 = c / chunks, (c + 1) / chunks
            res.extend(piece_paths(a[i] + (a[i + 1] - a[i]) * t0, b[i] + (b[i + 1] - b[i]) * t0,
                                   a[i] + (a[i + 1] - a[i]) * t1, b[i] + (b[i + 1] - b[i]) * t1))
    return res


class DecalWriter:
    # rails: the cable car rails with decals, [(polyline, road properties)] (BAIWriter.get_cable_car_rails)
    def __init__(self, scene_input: SceneInput, filepath, rails=None):
        self.scene_input = scene_input
        self.filepath = filepath
        self.rails = rails or []
        self.utils = Utils(self.scene_input)

    def get_strips(self):
        # (centre line, width, texture, name) of the decals of the scene and of the cable car rails
        res = []
        for obj in self.scene_input.get_object_list():
            if self.utils.get_object_type(obj) != "DECAL":
                continue
            pr = self.scene_input.get_property_container(obj)
            if pr.get("strip_pairs") == "1":
                continue
            points = [self.scene_input.get_vertex(obj, i) for i in range(self.scene_input.get_vertices_num(obj))]
            res.append((points, float(pr["width"]), pr["texture"], pr.get("original_name", pr["texture"])))
        for rail, rd_pr in self.rails:
            res.append((rail, float(rd_pr["cable_car_rail_width"]), rd_pr["cable_car_rail_decal"],
                        rd_pr.get("original_name", "") + " (cable car rail)"))
        return res

    def write(self):
        folder_path = self.filepath.replace(".psdl", "")
        file_path = folder_path + "/decals.pathset"
        paths = []
        for points, width, texture, name in self.get_strips():
            if len(texture) > MAX_NAME_LENGTH:
                report.warning("the texture of the decal " + name + " has a name longer than " + str(MAX_NAME_LENGTH)
                      + " characters, the decal is not exported")
                continue
            if width <= 0:
                report.warning("the decal " + name + " has no width, it is not exported")
                continue
            for path in strip_paths(points, width):
                for k in range(len(path) // 2):
                    if game_v(path, k) != k:
                        report.warning("the tiles of the decal " + name + " are stretched by the game")
                        break
                paths.append((texture, path))
        # Optional explicit edge pairs from evaluated editor geometry. Legacy centerline inputs remain unchanged.
        for obj in self.scene_input.get_object_list():
            pr = self.scene_input.get_property_container(obj)
            if self.utils.get_object_type(obj) != "DECAL" or pr.get("strip_pairs") != "1":
                continue
            texture = pr.get("texture", "")
            if not texture or len(texture) > MAX_NAME_LENGTH:
                report.warning("the decal has a missing or overlong texture name, it is not exported")
                continue
            points = [np.array(self.scene_input.get_vertex(obj, i), dtype=float) for i in range(self.scene_input.get_vertices_num(obj))]
            if len(points) < 4 or len(points) % 2:
                report.warning("the decal has invalid edge pairs, it is not exported")
                continue
            for i in range(0, len(points) - 2, 2):
                path, _ = path_points(*points[i:i + 4])
                if path is not None:
                    paths.append((texture, path))
        if len(paths) == 0:
            # no stale decals from a previous export
            if os.path.exists(file_path):
                os.remove(file_path)
            return
        if not os.path.exists(folder_path):
            os.mkdir(folder_path)
        file = BinaryFileHelper(file_path, 'wb')
        file.write_raw_string("PTH1")
        file.write_uint32(len(paths))
        file.write_uint32(0)
        for texture, path in paths:
            file.write_string32(texture)
            file.write_uint32(len(path))
            file.write_uint32(0)
            for p in path:
                file.write_uint32(0)  # room (not used by the game)
                for c in p:
                    file.write_float(c)
            file.write_byte(PATH_TYPE_LINE_STRIP)
            file.write_byte(PATH_SPACING)
            file.write_uint16(0)
        file.close()
        print(str(len(paths)) + " decal paths exported")
