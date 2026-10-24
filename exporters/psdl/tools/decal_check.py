# Checks decals.pathset files as the game reads them (see common/decal_writer.py)
#
#   python -I decal_check.py [--verbose] file.pathset [file2.pathset ...]
#
# For each path (decal): its texture, its points, whether the game draws it (at least 3 points), whether its faces
# point up as in the stock files, and how much its texture tiles are stretched: the game rounds v at each pair to
# whole tiles (the distance from the first point over the width of the first pair), so the stretch is how far the
# distance of each pair is from a whole number of tiles, and the pairs at less than half a tile from the previous
# one get its same v (the texture is smeared between them: the stock rails have them, harmless for a texture that
# doesn't change along the strip). Exits with 1 if a drawn decal is wrong (texture name too long, faces pointing
# down, no width).
# --verbose: also lists each path.

import math
import struct
import sys

import numpy as np

MAX_NAME_LENGTH = 31


def read_pathset(path):
    with open(path, 'rb') as f:
        d = f.read()
    if d[:4] != b'PTH1':
        raise Exception(path + " is not a pathset file")
    n = struct.unpack_from('<I', d, 4)[0]
    o = 12
    res = []
    for _ in range(n):
        name = d[o:o + 32].split(b'\0')[0].decode('latin1')
        o += 32
        count = struct.unpack_from('<I', d, o)[0]
        o += 8
        points = [np.array(struct.unpack_from('<fff', d, o + 16 * k + 4)) for k in range(count)]
        o += 16 * count + 4
        res.append((name, points))
    return res


def check_path(name, points):
    # (drawn, problems, info)
    if len(points) < 3:
        return False, [], "not drawn (" + str(len(points)) + " points)"
    problems = []
    if len(name) > MAX_NAME_LENGTH:
        problems.append("texture name longer than " + str(MAX_NAME_LENGTH) + " characters")
    if np.cross(points[1] - points[0], points[2] - points[0])[1] <= 0:
        problems.append("faces pointing down")
    width = float(np.linalg.norm(points[1] - points[0]))
    if width < 1e-6:
        problems.append("no width")
        return True, problems, ""
    stretch = 0.0
    prev_v = 0
    smeared = 0
    for k in range(1, len(points) // 2):
        d = float(np.linalg.norm(points[2 * k] - points[0])) / width
        v = math.floor(d + 0.5)
        if v <= prev_v:
            smeared += 1
        stretch = max(stretch, abs(d - v))
        prev_v = v
    info = "width {:.2f} m, {} tiles, stretch {:.2f} tiles".format(width, prev_v, stretch)
    if smeared > 0:
        info += ", " + str(smeared) + " pairs with the v of the previous one"
    return True, problems, info


def main(args):
    verbose = '--verbose' in args
    files = [a for a in args if not a.startswith('--')]
    if not files:
        print(__doc__ if __doc__ else "usage: decal_check.py [--verbose] file.pathset ...")
        return 2
    failed = False
    for path in files:
        paths = read_pathset(path)
        drawn = 0
        textures = {}
        print("== " + path + ": " + str(len(paths)) + " paths")
        for i, (name, points) in enumerate(paths):
            is_drawn, problems, info = check_path(name, points)
            drawn += int(is_drawn)
            if is_drawn:
                textures[name] = textures.get(name, 0) + 1
            if problems:
                failed = True
            if verbose or problems:
                print("  {:3} {:28} {:3} points  {}{}".format(i, name, len(points), info,
                                                              ("  ERROR: " + ", ".join(problems)) if problems else ""))
        print("  " + str(drawn) + " drawn: " + ", ".join(k + " x" + str(v) for k, v in sorted(textures.items())))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
