# The room of a position, as midtown2.exe looks it up (the PSDL block whose perimeter contains it): for the opponents
# (see opponents.py) and for the BAI roads and intersections without geometry of their own (see
# JsonProcessor.resolve_traffic_rooms), which are in the rooms they lie over.
#
# Positions are in the coordinates of the program (x, y up, z).

import numpy as np


class RoomFinder:
    # the room of a position, as JsonProcessor.find_block (the block whose perimeter contains it, the nearest in height
    # if several do), with the bounds of the blocks tested at once
    def __init__(self, jp):
        self.jp = jp
        perimeters = jp.block_perimeters
        bounds = jp.block_perimeters_bounds
        self.bounds = np.array([b if b is not None else [[np.inf, np.inf], [-np.inf, -np.inf]] for b in bounds],
                               dtype=float).reshape(-1, 2, 2)
        self.heights = [None] * len(perimeters)

    def room_of(self, pos):
        if len(self.bounds) == 0:
            return 0
        x, z = float(pos[0]), float(pos[2])
        b = self.bounds
        candidates = np.nonzero((x >= b[:, 0, 0]) & (x <= b[:, 1, 0]) & (z >= b[:, 0, 1]) & (z <= b[:, 1, 1]))[0]
        jp = self.jp
        best, best_dist = 0, None
        for i in candidates:
            block = jp.block_perimeters[i][0]
            if not any(jp.is_point_inside_polygon(pos, polygon) for polygon in block):
                continue
            if self.heights[i] is None:
                self.heights[i] = jp.get_block_height(block)
            dist = abs(float(pos[1]) - self.heights[i])
            if best_dist is None or dist < best_dist:
                best, best_dist = int(i) + 1, dist
        return best
