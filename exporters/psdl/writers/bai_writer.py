# Writes the BAI network of the city (traffic/model.py), the paths of the ambient traffic, of the pedestrians and of the
# cable cars. Info here: https://github.com/Dummiesman/angel-file-formats/blob/master/Midtown%20Madness%202/BAI.md
# The values that page leaves unexplained (lane offsets and boundaries, distances, tangents, flags, section density)
# follow the stock sf.bai and london.bai (tools/bai_check.py checks them)

import math
import struct

import numpy as np

from scene import Scene, to_writer_space, to_writer_rotation, euler
from traffic.model import BaiNetwork
from .file_io import BinaryFileHelper
from . import report

# the writer works in a z-up space, BinaryFileHelper.write_vec3 converts it to the y-up space of the file
UP = np.array([0.0, 0.0, 1.0])
# the stock roads have a section 15 m from each end, and at least 4 sections
END_SECTION_LENGTH = 15.0
END_SECTION_MIN_EXCESS = 5.0
MIN_SECTIONS = 4
# the game moves vehicles and pedestrians along a 2D Hermite curve between consecutive sections, with the directions
# at each section following its neighbours, so a long segment ending at a sharp corner bulges out of the road: a
# section 2 m from each side of the corners keeps the long segments straight and the bulge within those 2 m
CORNER_SECTION_DISTANCE = 2.0
CORNER_MIN_ANGLE = math.radians(10.0)
# the pedestrians aim at the point 6 m ahead on the curve of the sidewalk segment they're on (the curve of the
# segment from sidewalk point i to j has the road tangents i and j times the segment length), even past the end of
# the segment, so on a short segment that turns the aim flies off and they wander away or circle (the cars don't):
# the sidewalk points of the sections near the corners move back along the corner sides, so that the segments
# touching a corner are at least 16 m long, the ones moved back on a straight line (where the curve stays on it) at
# least 0.5 m apart (a pedestrian simulation shows this works up to corners of about 120 degrees, sharper ones need
# the turn spread over more road points)
SIDEWALK_CORNER_SEGMENT = 16.0
SIDEWALK_MIN_SEGMENT = 0.5
# the lane boundaries list has 10 floats, enough for 4 lanes
NUM_LANE_BOUNDARIES = 10
MAX_LANES_PER_SIDE = 4
# the ambient cars turning at an intersection keep the roads they can turn onto in two arrays of 10 (0x538A10 in
# midtown2.exe), so the game crashes on intersections with more than 11 roads
MAX_INTERSECTION_ROADS = 11
CDCD_FLOAT = struct.unpack('<f', b'\xcd\xcd\xcd\xcd')[0]
CDCDCDCD = 0xcdcdcdcd
BASE_SPEED = 15.0

FLAG_DIVIDED = 1
FLAG_ALLEY = 2
FLAG_FREEWAY = 4
FLAG_FLAT = 8


def normalized(v):
    length = np.linalg.norm(v)
    return np.divide(v, length) if length > 1e-9 else np.array(v, dtype=float)


def cumulative_lengths(points):
    res = [0.0]
    for i in range(1, len(points)):
        res.append(res[-1] + float(np.linalg.norm(np.subtract(points[i], points[i - 1]))))
    return res


def section_frames(centre, up=UP):
    # the coordinate system of each section: z points back along the previous segment, y is the up vector made
    # orthogonal to it, x = z cross y points to the right side; the tangent is the mean of the two segments
    n = len(centre)
    segments = [normalized(np.subtract(centre[i + 1], centre[i])) for i in range(n - 1)]
    xs, ys, zs, tangents = [], [], [], []
    for i in range(n):
        prev_seg = segments[i - 1] if i > 0 else segments[0]
        next_seg = segments[i] if i < n - 1 else segments[-1]
        z = -prev_seg
        y = normalized(np.subtract(up, np.dot(up, z) * z))
        xs.append(np.cross(z, y))
        ys.append(y)
        zs.append(z)
        tangent = normalized(np.add(prev_seg, next_seg))
        tangents.append(tangent if np.linalg.norm(tangent) > 0.5 else next_seg)
    return xs, ys, zs, tangents


def lateral_offsets(points, centre, x_axis):
    # the distances of the points from the centre line, along the x axis of the section
    return [abs(float(np.dot(np.subtract(p, centre), x_axis))) for p in points]


def lane_boundaries(offsets, half_width):
    # -half width, the boundary after each lane (twice: midway to the next lane or to the sidewalk), half width,
    # then padding (the offsets are the ones of the lanes, inner first, and of the sidewalk)
    res = [-half_width]
    for k in range(len(offsets) - 1):
        b = (offsets[k] + offsets[k + 1]) / 2
        res.extend([b, b])
    res.append(half_width)
    return res + [CDCD_FLOAT] * (NUM_LANE_BOUNDARIES - len(res))


def interpolate(points, u):
    # the point of a polyline at the parameter u (section index plus fraction to the next one)
    i = min(int(math.floor(u)), len(points) - 2)
    t = u - i
    return np.add(np.multiply(points[i], 1.0 - t), np.multiply(points[i + 1], t))


def turn_angle(a, b, c):
    # the angle between the segments a-b and b-c, on the ground, as the game's curves are 2D
    dir_prev = np.subtract(b, a)[:2]
    dir_next = np.subtract(c, b)[:2]
    if np.linalg.norm(dir_prev) < 1e-9 or np.linalg.norm(dir_next) < 1e-9:
        return 0.0
    return math.acos(max(-1.0, min(1.0, float(np.dot(normalized(dir_prev), normalized(dir_next))))))


def corner_indices(centre):
    # the sections where the road turns by at least CORNER_MIN_ANGLE
    return [i for i in range(1, len(centre) - 1) if turn_angle(centre[i - 1], centre[i], centre[i + 1]) >= CORNER_MIN_ANGLE]


def corner_parameters(centre, lengths):
    # the parameters of the sections around the sharp corners (see CORNER_SECTION_DISTANCE), on the segments long
    # enough to bulge noticeably
    res = []
    for i in corner_indices(centre):
        len_prev = lengths[i] - lengths[i - 1]
        len_next = lengths[i + 1] - lengths[i]
        if len_prev > 2 * CORNER_SECTION_DISTANCE:
            res.append(i - CORNER_SECTION_DISTANCE / len_prev)
        if len_next > 2 * CORNER_SECTION_DISTANCE:
            res.append(i + CORNER_SECTION_DISTANCE / len_next)
    return res


def point_at_length(points, lengths, s):
    # the point of a polyline at the length s along it (lengths are its cumulative lengths)
    for i in range(len(points) - 1):
        if lengths[i + 1] >= s or i == len(points) - 2:
            seg = lengths[i + 1] - lengths[i]
            return interpolate(points, i + ((s - lengths[i]) / seg if seg > 0 else 0.0))


def spread_corner_points(points, corners):
    # the sidewalk centre with the points near the corners moved back along the corner sides (see
    # SIDEWALK_CORNER_SEGMENT): the ones within 16 m of a corner, but at most halfway to the next corner, move between
    # 16 m (less if there's no room) and the first point that stays, evenly
    n = len(points)
    lengths = cumulative_lengths([np.array(p[:2], dtype=float) for p in points])
    res = [np.array(p, dtype=float) for p in points]
    for k, c in enumerate(corners):
        for step in (-1, 1):
            if 0 <= k + step < len(corners):
                neighbour = corners[k + step]
                limit = abs(lengths[neighbour] - lengths[c]) / 2
            else:
                neighbour = 0 if step < 0 else n - 1
                limit = abs(lengths[neighbour] - lengths[c])
            near = []
            j = c + step
            while j != neighbour and abs(lengths[j] - lengths[c]) < min(SIDEWALK_CORNER_SEGMENT, limit):
                near.append(j)
                j += step
            if len(near) == 0:
                continue
            boundary = min(abs(lengths[j] - lengths[c]), limit)
            first = min(SIDEWALK_CORNER_SEGMENT, max(boundary - len(near) * SIDEWALK_MIN_SEGMENT,
                                                     boundary / (len(near) + 1)))
            for m, j in enumerate(near):
                s = first + (boundary - first) * m / len(near)
                res[j] = point_at_length(points, lengths, lengths[c] + step * s)
    return res


def resampled_parameters(centre):
    # the sections of a road as parameters along its sections (see interpolate), with the ones added around the sharp
    # corners and the ones added to follow the stock roads: one 15 m from each end (unless that leaves less than
    # 5 m), the short roads split in three, and at least 4 sections
    lengths = cumulative_lengths(centre)
    total = lengths[-1]
    params = [float(i) for i in range(len(centre))]
    if total <= 0 or len(centre) < 2:
        return params
    params += corner_parameters(centre, lengths)

    def param_at(s):
        for i in range(len(lengths) - 1):
            if lengths[i + 1] >= s:
                seg = lengths[i + 1] - lengths[i]
                return i + ((s - lengths[i]) / seg if seg > 0 else 0.0)
        return float(len(lengths) - 1)

    if total < 2 * END_SECTION_LENGTH:
        if len(centre) < MIN_SECTIONS:
            params += [param_at(total / 3), param_at(2 * total / 3)]
    else:
        if lengths[1] > END_SECTION_LENGTH + END_SECTION_MIN_EXCESS:
            params.append(param_at(END_SECTION_LENGTH))
        if total - lengths[-2] > END_SECTION_LENGTH + END_SECTION_MIN_EXCESS:
            params.append(param_at(total - END_SECTION_LENGTH))
    params = sorted(set(params))
    while len(params) < MIN_SECTIONS:
        # split the longest segment
        points = [interpolate(centre, u) for u in params]
        seg_lengths = [np.linalg.norm(np.subtract(points[i + 1], points[i])) for i in range(len(points) - 1)]
        k = int(np.argmax(seg_lengths))
        params.insert(k + 1, (params[k] + params[k + 1]) / 2)
    return params


def to_writer(p):
    # a position of the program in the space of the writer, rounded to 32 bit floats as the parts (see scene.py)
    return np.array(to_writer_space(p), dtype=float)


def side_traffic_type(road, right):
    # the ambients of a side: 0 cars and pedestrians, 1 pedestrians, 2 cars, 3 nothing
    side = road.paths.right if right else road.paths.left
    pedestrians = road.pedestrians[0 if right else 1]
    traffic_type = road.traffic_type
    if len(side.lanes) == 0:
        if traffic_type == 0 or (traffic_type == 1 and pedestrians):
            traffic_type = 1
        else:
            traffic_type = 3
    elif traffic_type == 0 and (not pedestrians or not road.geo_sidewalks):
        traffic_type = 2
    return traffic_type


class RouteSide:
    # a side of a road in the space of the writer, from the start to the end of the road
    def __init__(self, side):
        self.outer = [to_writer(p) for p in side.outer]
        self.curb = [to_writer(p) for p in side.curb]
        self.lanes = [[to_writer(p) for p in lane] for lane in side.lanes]
        self.sidewalk = [to_writer(p) for p in side.sidewalk] if side.sidewalk is not None else None
        self.rail = [to_writer(p) for p in side.rail] if side.rail is not None else None

    def resampled(self, params):
        res = RouteSide.__new__(RouteSide)
        for name in ('outer', 'curb', 'sidewalk', 'rail'):
            points = getattr(self, name)
            setattr(res, name, [interpolate(points, u) for u in params] if points is not None else None)
        res.lanes = [[interpolate(lane, u) for u in params] for lane in self.lanes]
        return res


def centre_line(right, left):
    # midway between the outer edges, at the height of the road (midway between the curbs)
    res = []
    for ro, rc, lc, lo in zip(right.outer, right.curb, left.curb, left.outer):
        c = np.divide(np.add(ro, lo), 2)
        c[2] = (rc[2] + lc[2]) / 2
        res.append(c)
    return res


class Route:
    # the geometry of a BAI road as written (see BaiRoad): resampled, with the frames of the sections, the paths of the
    # pedestrians and the rails
    def __init__(self, road):
        right, left = RouteSide(road.paths.right), RouteSide(road.paths.left)
        for side in (right, left):
            if len(side.lanes) > MAX_LANES_PER_SIDE:
                report.warning("the BAI road of " + road.name + " has more than " + str(MAX_LANES_PER_SIDE)
                               + " lanes on a side, the outer ones are not exported", element=report.element_name(road.name), kind="road")
                del side.lanes[MAX_LANES_PER_SIDE:]
        params = resampled_parameters(centre_line(right, left))
        self.right, self.left = right.resampled(params), left.resampled(params)
        self.centre = centre_line(self.right, self.left)
        self.x, self.y, self.z, self.tangents = section_frames(self.centre)
        self.half_width = float(np.linalg.norm(np.subtract(self.right.outer[0], self.left.outer[0]))) / 2
        corners = corner_indices(self.centre)
        for side, sign in ((self.right, 1), (self.left, -1)):
            # the pedestrians: on the path drawn in the editor, or midway between the curb and the outer edge
            sidewalk = side.sidewalk or [np.divide(np.add(a, b), 2) for a, b in zip(side.curb, side.outer)]
            side.sidewalk = spread_corner_points(sidewalk, corners)
            if road.cable_car and side.rail is None:
                side.rail = [np.add(c, np.multiply(x, sign * road.cable_car_offset)) for c, x in zip(self.centre, self.x)]
            elif not road.cable_car:
                side.rail = None
        self.flags = self.get_flags(road)

    def num_sections(self):
        return len(self.centre)

    def get_flags(self, road):
        flags = 0
        if road.divided:
            flags |= FLAG_DIVIDED
        if road.alley:
            flags |= FLAG_ALLEY
        if road.freeway:
            flags |= FLAG_FREEWAY
        if all(abs(float(np.dot(z, UP))) < 1e-3 for z in self.z):
            flags |= FLAG_FLAT
        return flags


def section_points(road):
    # the points of the sections of a road (its edges, curbs and lanes, not resampled), in the space of the writer
    return [to_writer(p) for side in (road.paths.right, road.paths.left) for line in [side.outer, side.curb] + side.lanes for p in line]


def bounding_box(vertices, add):
    # the bounding box of the vertices, with its size increased in each direction by add
    lo = [float('inf')] * 3
    hi = [float('-inf')] * 3
    for v in vertices:
        for a in range(3):
            if v[a] > hi[a]:
                hi[a] = v[a]
            if v[a] < lo[a]:
                lo[a] = v[a]
    return [[c - add for c in lo], [c + add for c in hi]]


def boxes_intersect(b1, b2):
    return not any(b2[0][a] > b1[1][a] or b2[1][a] < b1[0][a] for a in range(3))


def rotate_point(point, centre, angle):
    # rotated around the z axis through the centre
    cos_theta = math.cos(angle)
    sin_theta = math.sin(angle)
    x = (cos_theta * (point[0] - centre[0])) - (sin_theta * (point[1] - centre[1])) + centre[0]
    y = (sin_theta * (point[0] - centre[0])) + (cos_theta * (point[1] - centre[1])) + centre[1]
    return [x, y, point[2]]


def vector_projection(a, b, c):
    # the projection of c on the line from a to b
    ac = np.subtract(c, a)
    ab = np.subtract(b, a)
    n = ab / np.linalg.norm(ab)
    return np.add(np.multiply(np.dot(ac, n), n), a)


# the parts of a room whose vertices give its size for the culling of the roads
CULLING_PARTS = ["ROADS", "ROADN", "ROADSN", "ROADD", "ROADDN", "BLOCK", "IS", "NUL"]
LARGE_BUBBLE = 200.0
SMALL_BUBBLE = 100.0


class BAIWriter:
    # writes the BAI network of the city (see traffic/model.py), with the rooms of the scene (see scene.py)
    def __init__(self, scene: Scene, network: BaiNetwork, filepath, accurate_culling):
        self.scene = scene
        self.network = network
        self.filepath = filepath
        self.accurate_culling = accurate_culling

    def warn_cable_car_lines_without_ends(self):
        # aiMap::Init puts a cable car (va_cablecar_f) only on the intersections where exactly one of the roads has
        # rails (the 4 ends of the San Francisco lines), so a line that is only a closed loop gets none
        cable_roads = [road for road in self.network.roads if road.cable_car]
        if len(cable_roads) == 0:
            return
        line_of = {road.index: road.index for road in cable_roads}

        def find(i):
            while line_of[i] != i:
                i = line_of[i]
            return i

        line_ends = set()
        for intersection in self.network.intersections:
            ends = [road.index for road, _ in intersection.roads if road.cable_car]
            for i in ends[1:]:
                line_of[find(i)] = find(ends[0])
            if len(ends) == 1:
                line_ends.add(ends[0])
        lines = {}
        for road in cable_roads:
            lines.setdefault(find(road.index), []).append(road)
        for line in lines.values():
            if not any(road.index in line_ends for road in line):
                names = ', '.join(road.name for road in line)
                report.warning("the cable car line of " + names + " has no ends, MM2 puts a cable car only at each end"
                               + " of a line (an intersection where only one cable car road arrives), so it will have no cable cars")

    def automatic_traffic_light(self, road, end_index, index_in_intersection):
        # As in MM2, the traffic light is on the opposite road: the one 2 places after this road in the list of the
        # intersection (the opposite one with 4 roads), skipping the roads without traffic; near its curb, on the side of
        # the lanes leaving the intersection
        end = road.end if end_index == 1 else road.start
        intersection = end.intersection
        roads = [r for r, _ in intersection.roads]
        if len(roads) == 0:
            report.warning("no roads available for automatic traffic light placement")
            return (np.zeros(3), np.zeros(3))
        road_2 = None
        for step in range(len(roads)):
            candidate = roads[(index_in_intersection + 2 + step) % len(roads)]
            if candidate.traffic_type == 3 and (len(candidate.paths.right.lanes) == 0 or len(candidate.paths.left.lanes) == 0):
                continue
            road_2 = candidate
            break
        if road_2 is None:
            report.warning("no traffic road available for automatic traffic light placement")
            return (np.zeros(3), np.zeros(3))
        right_2, left_2 = road_2.paths.right, road_2.paths.left
        if road_2.end.intersection is intersection:
            vo1, vo2 = to_writer(right_2.curb[-1]), to_writer(right_2.outer[-1])
        else:
            vo1, vo2 = to_writer(left_2.curb[0]), to_writer(left_2.outer[0])
        vo = np.divide(np.add(np.multiply(vo1, 3), vo2), 4)
        right, left = road.paths.right, road.paths.left
        if end_index == 0:
            a, b = to_writer(left.outer[0]), to_writer(right.outer[0])
        else:
            a, b = to_writer(right.outer[-1]), to_writer(left.outer[-1])
        vd = rotate_point(vector_projection(a, b, vo), vo, np.deg2rad(90.0))
        return (vo, vd)

    def write_road_end(self, road, end_index):
        # end_index: 0 start, 1 end
        file = self.file
        end = road.end if end_index == 1 else road.start
        intersection = end.intersection
        if intersection is None:
            # a free end
            file.write_uint32(CDCDCDCD)
            file.write_uint16(0xcdcd)
            file.write_uint32(2)
            file.write_uint32(CDCDCDCD)
        else:
            index_in_intersection = intersection.position_of(road, end_index == 0)
            if index_in_intersection < 0:
                raise Exception("the BAI road of " + road.name + " is not in the list of the intersection " + intersection.name)
            file.write_uint32(intersection.index)
            file.write_uint16(0xcdcd)
            file.write_uint32(end.rule)
            file.write_uint32(index_in_intersection)
        if end.rule == 1 and intersection is not None:
            if end.traffic_light is not None:
                # placed by hand: the light looks along its x axis
                position, rotation = end.traffic_light
                vo = to_writer_space(position)
                heading = euler(to_writer_rotation(rotation))[2]
                vd = rotate_point([vo[0] - 1.0, vo[1], vo[2]], vo, heading)
            else:
                vo, vd = self.automatic_traffic_light(road, end_index, index_in_intersection)
            # the axis is a point 1 m from the light
            vd = np.add(vo, normalized(np.subtract(vd, vo)))
            file.write_vec3(vo)
            file.write_vec3(vd)
        else:
            # no traffic light
            for i in range(6):
                file.write_float(0.0)

    def write_road_side(self, road, route, is_right_side):
        # the lanes, sidewalk and rail of a side (the right side lanes and rail from the end to the start)
        file = self.file
        side = route.right if is_right_side else route.left
        if is_right_side:
            lanes = [list(reversed(lane)) for lane in side.lanes]
            rails = [list(reversed(side.rail))] if side.rail is not None else []
        else:
            lanes = side.lanes
            rails = [side.rail] if side.rail is not None else []

        file.write_uint16(len(lanes))
        file.write_uint16(len(rails))
        file.write_uint16(0)  # trains
        file.write_uint16(1)  # sidewalks
        file.write_uint16(side_traffic_type(road, is_right_side))

        # distances along each lane and along the sidewalk
        for lane in lanes:
            for d in cumulative_lengths(lane):
                file.write_float(d)
        for d in cumulative_lengths(side.sidewalk):
            file.write_float(d)

        # distances of the lanes (inner first) and of the sidewalk from the centre line, then the lane boundaries
        first_points = [lane[-1] if is_right_side else lane[0] for lane in lanes] + [side.sidewalk[0]]
        offsets = lateral_offsets(first_points, route.centre[0], route.x[0])
        for d in offsets:
            file.write_float(d)
        for d in lane_boundaries(offsets, route.half_width):
            file.write_float(d)

        for line in lanes + [side.sidewalk] + rails + [side.curb, side.outer]:
            for v in line:
                file.write_vec3(v)

    def write_road(self, road):
        file = self.file
        route = Route(road)
        file.write_uint16(road.index)
        file.write_uint16(route.num_sections())
        file.write_uint16(route.flags)
        file.write_uint16(len(road.rooms))
        for room in road.rooms:
            file.write_uint16(self.scene.block_index(room) + 1)
        file.write_float(route.half_width)
        file.write_float(BASE_SPEED)
        self.write_road_side(road, route, True)
        self.write_road_side(road, route, False)
        for d in cumulative_lengths(route.centre):
            file.write_float(d)
        for line in [route.centre, route.x, route.y, route.z, route.tangents]:
            for v in line:
                file.write_vec3(v)
        self.write_road_end(road, 1)
        self.write_road_end(road, 0)

    def write_intersection(self, intersection):
        file = self.file
        if len(intersection.roads) > MAX_INTERSECTION_ROADS:
            report.warning("a BAI intersection has " + str(len(intersection.roads)) + " roads, more than "
                           + str(MAX_INTERSECTION_ROADS) + ": the ambient traffic of the game crashes on it",
                           element=report.element_name(intersection.name), kind="intersection")
        file.write_uint16(intersection.index)
        file.write_uint16(self.scene.block_index(intersection.room) + 1)
        file.write_vec3(to_writer(intersection.centre))
        file.write_uint16(len(intersection.roads))
        for road, _ in intersection.roads:
            file.write_uint32(road.index)

    def get_culling(self):
        # the roads near each room (the game draws their ambients when the room is visible): within 100 m (small) and
        # 200 m (large) of the room, by bounding box, or by distance between the vertices with accurate culling
        blocks = self.scene.blocks
        block_parts = [[] for _ in blocks]
        for part in self.scene.parts:
            i = self.scene.block_index(part.block)
            if i >= 0 and part.type in CULLING_PARTS:
                block_parts[i].append(part)
        road_points = [section_points(road) for road in self.network.roads]
        road_boxes_large = [bounding_box(points, LARGE_BUBBLE / 2) for points in road_points]
        road_boxes_small = [bounding_box(points, SMALL_BUBBLE / 2) for points in road_points]
        cull_large_list = []
        cull_small_list = []
        for parts in block_parts:
            cull_large = []
            cull_small = []
            block_vertices = [v for part in parts for v in part.vertices]
            box_large = bounding_box(block_vertices, LARGE_BUBBLE / 2)
            box_small = bounding_box(block_vertices, SMALL_BUBBLE / 2)
            for i, points in enumerate(road_points):
                if not boxes_intersect(box_large, road_boxes_large[i]):
                    continue
                if self.accurate_culling:
                    vertices = np.array(block_vertices, dtype=float)
                    distance = min(float(np.min(np.linalg.norm(vertices - vr, axis=1))) for vr in points)
                    if distance < SMALL_BUBBLE:
                        cull_small.append(i)
                        cull_large.append(i)
                    elif distance < LARGE_BUBBLE:
                        cull_large.append(i)
                else:
                    cull_large.append(i)
                    if boxes_intersect(box_small, road_boxes_small[i]):
                        cull_small.append(i)
            cull_large_list.append(cull_large)
            cull_small_list.append(cull_small)
        return cull_large_list, cull_small_list

    def write(self):
        self.warn_cable_car_lines_without_ends()
        print("writing the bai...")
        self.file = BinaryFileHelper(self.filepath.replace(".psdl", ".bai"), 'wb')
        file = self.file
        file.write_raw_string("CAI1")
        file.write_uint16(len(self.network.intersections))
        file.write_uint16(len(self.network.roads))
        for road in self.network.roads:
            self.write_road(road)
        for intersection in self.network.intersections:
            self.write_intersection(intersection)
        # the culling lists of each room, after an empty one for room 0
        blocks = self.scene.blocks
        file.write_uint32(len(blocks) + 1)
        for cull_list in self.get_culling():
            file.write_uint16(0)
            for roads in cull_list:
                file.write_uint16(len(roads))
                for i in roads:
                    file.write_uint16(i)
        file.close()
        print("BAI Exported!")
