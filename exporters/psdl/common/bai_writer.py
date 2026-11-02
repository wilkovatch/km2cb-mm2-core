# Info here: https://github.com/Dummiesman/angel-file-formats/blob/master/Midtown%20Madness%202/BAI.md
# The values that page leaves unexplained (lane offsets and boundaries, distances, tangents, flags, section density)
# follow the stock sf.bai and london.bai (the tools/bai_check.py script of the km2cb MM2 core checks them)

import math
import struct

import numpy as np

from .scene_input import SceneInput
from .file_io import BinaryFileHelper
from .utils import Utils
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

# the decals of the cable car rails go on through an intersection from a road into another one when their directions
# towards it are more than 60 degrees apart, along a curve with points about every 2 m
RAIL_JOIN_MAX_DOT = 0.5
RAIL_JOIN_STEP = 2.0

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


class RouteGeometry:
    # the polylines of a BAI road, from its start to its end (the right side is the one of the lanes going from the end
    # to the start), lanes inner first; the curb is the inner edge of the sidewalk (the outer edge without sidewalks)
    def __init__(self):
        self.right_outer = []
        self.right_curb = []
        self.left_curb = []
        self.left_outer = []
        self.right_lanes = []
        self.left_lanes = []

    def polylines(self):
        return [self.right_outer, self.right_curb, self.left_curb, self.left_outer] + self.right_lanes + self.left_lanes

    def num_sections(self):
        return len(self.right_outer)

    def centre(self):
        # midway between the outer edges, at the height of the road (midway between the curbs)
        res = []
        for ro, rc, lc, lo in zip(self.right_outer, self.right_curb, self.left_curb, self.left_outer):
            c = np.divide(np.add(ro, lo), 2)
            c[2] = (rc[2] + lc[2]) / 2
            res.append(c)
        return res

    def resampled(self, params):
        res = RouteGeometry()
        for name in ('right_outer', 'right_curb', 'left_curb', 'left_outer'):
            setattr(res, name, [interpolate(getattr(self, name), u) for u in params])
        res.right_lanes = [[interpolate(lane, u) for u in params] for lane in self.right_lanes]
        res.left_lanes = [[interpolate(lane, u) for u in params] for lane in self.left_lanes]
        return res


class BAIWriter:
    def __init__(self, scene_input: SceneInput, filepath, accurate_culling):
        self.scene_input = scene_input
        self.filepath = filepath
        self.accurate_culling = accurate_culling
        self.utils = Utils(self.scene_input)

    def prop(self, obj):
        return self.scene_input.get_property_container(obj)

    def verts_distance(self, v1, v2):
        return np.linalg.norm(np.subtract(v1, v2))

    def vector_projection(self, oA, oB, oC):
        A = np.subtract(oC, oA)
        B = np.subtract(oB, oA)
        NB = self.utils.get_normal(B)
        C = np.multiply(np.dot(A, NB), NB)
        return np.add(C, oA)

    def rotate_point(self, point_to_rotate, center_point, angleRad):
        pR = point_to_rotate
        pC = center_point
        theta = angleRad
        cos_theta = math.cos(theta)
        sin_theta = math.sin(theta)
        X = (cos_theta * (pR[0] - pC[0])) - (sin_theta * (pR[1] - pC[1])) + pC[0]
        Y = (sin_theta * (pR[0] - pC[0])) + (cos_theta * (pR[1] - pC[1])) + pC[1]
        return [X, Y, pR[2]]

    def get_which_sides_have_sidewawlks(self, value):
        if ":" in value:
            parts = value.split(":")
            return [int(parts[0]), int(parts[1])]
        else:
            res = int(value)
            return [res, res]

    def get_intersection_center(self, IS):
        vertices_sum = 0
        verts_num = self.scene_input.get_vertices_num(IS)
        for i in range(verts_num):
            vertices_sum = np.add(vertices_sum, self.scene_input.get_vertex(IS, i))
        return np.divide(vertices_sum, verts_num)

    def get_lane_counts(self, rd):
        # the lanes of the right and left side (the left_lanes property goes to the right side)
        rd_pr = self.prop(rd)
        return int(rd_pr["left_lanes"]), int(rd_pr["right_lanes"])

    def get_route_geometry(self, rd):
        rd_pr = self.prop(rd)
        vps = int(rd_pr["vertices_per_section"])
        num_verts = self.scene_input.get_vertices_num(rd)
        verts = [np.array(self.scene_input.get_vertex(rd, i), dtype=float) for i in range(num_verts)]
        sections = [verts[i * vps:(i + 1) * vps] for i in range(num_verts // vps)]
        n_right, n_left = self.get_lane_counts(rd)
        geo = RouteGeometry()
        if rd_pr.get("bai_layout", "1") == "2":
            # each section: right outer edge, right curb, the lanes from the right to the left, left curb, left outer edge
            for s in sections:
                geo.right_outer.append(s[0])
                geo.right_curb.append(s[1])
                geo.left_curb.append(s[-2])
                geo.left_outer.append(s[-1])
            geo.right_lanes = [[s[1 + n_right - k] for s in sections] for k in range(n_right)]
            geo.left_lanes = [[s[2 + n_right + k] for s in sections] for k in range(n_left)]
            return geo

        # each section: the outer edges, the curbs if there are sidewalks, the divider edges if there is a divider,
        # with the lanes spread evenly between them
        has_geo_sidewalks = int(rd_pr["has_geo_sidewalks"]) > 0
        divided = vps == 6 or (vps == 4 and not has_geo_sidewalks)
        right_inner = []
        left_inner = []
        for s in sections:
            rc = s[1] if has_geo_sidewalks else s[0]
            lc = s[-2] if has_geo_sidewalks else s[-1]
            geo.right_outer.append(s[0])
            geo.right_curb.append(rc)
            geo.left_curb.append(lc)
            geo.left_outer.append(s[-1])
            if divided:
                right_inner.append(s[2] if has_geo_sidewalks else s[1])
                left_inner.append(s[3] if has_geo_sidewalks else s[2])
            else:
                mid = np.divide(np.add(rc, lc), 2)
                right_inner.append(mid if n_left > 0 else lc)
                left_inner.append(mid if n_right > 0 else rc)

        def spread(inner, curb, n):
            return [[np.add(a, np.multiply(np.subtract(b, a), (k + 0.5) / n)) for a, b in zip(inner, curb)] for k in range(n)]

        geo.right_lanes = spread(right_inner, geo.right_curb, n_right)
        geo.left_lanes = spread(left_inner, geo.left_curb, n_left)
        return geo

    def get_route(self, rd):
        # the resampled geometry of a road and its derived data
        rd_pr = self.prop(rd)
        name = rd_pr.get("original_name", rd_pr["id"])
        geo = self.get_route_geometry(rd)
        for lanes in (geo.right_lanes, geo.left_lanes):
            if len(lanes) > MAX_LANES_PER_SIDE:
                report.warning(name + " has more than " + str(MAX_LANES_PER_SIDE) + " lanes on a side, the outer ones are not exported to the BAI",
                               element=report.element_name(name), kind="road")
                del lanes[MAX_LANES_PER_SIDE:]
        geo = geo.resampled(resampled_parameters(geo.centre()))
        centre = geo.centre()
        xs, ys, zs, tangents = section_frames(centre)
        route = {
            'geo': geo,
            'centre': centre,
            'x': xs,
            'y': ys,
            'z': zs,
            'tangents': tangents,
            'half_width': float(np.linalg.norm(np.subtract(geo.right_outer[0], geo.left_outer[0]))) / 2,
            'rails': [],
        }
        corners = corner_indices(centre)
        for side, curb, outer in (('right', geo.right_curb, geo.right_outer), ('left', geo.left_curb, geo.left_outer)):
            mid = [np.divide(np.add(a, b), 2) for a, b in zip(curb, outer)]
            route[side + '_sidewalk'] = spread_corner_points(mid, corners)
        route['flags'] = self.get_flags(rd, zs)
        if rd_pr.get("cable_car", "0") == "1":
            offset = float(rd_pr.get("cable_car_offset", "2.5"))
            route['rails'] = [
                [np.add(c, np.multiply(x, offset)) for c, x in zip(centre, xs)],
                [np.subtract(c, np.multiply(x, offset)) for c, x in zip(centre, xs)],
            ]
        return route

    def warn_cable_car_lines_without_ends(self):
        # aiMap::Init puts a cable car (va_cablecar_f) only on the intersections where exactly one of the roads has
        # rails (the 4 ends of the San Francisco lines), so a line that is only a closed loop gets none
        cable_roads = {}
        for rd in self.roads_finished:
            rd_pr = self.prop(rd)
            if rd_pr.get("cable_car", "0") == "1":
                cable_roads[rd_pr["id"]] = rd_pr
        if len(cable_roads) == 0:
            return
        line_of = {rd_id: rd_id for rd_id in cable_roads}

        def find(rd_id):
            while line_of[rd_id] != rd_id:
                rd_id = line_of[rd_id]
            return rd_id

        line_ends = set()
        for IS in self.intersections_finished:
            is_cable_roads = [r for r in self.prop(IS)["roads"].split(";") if r in cable_roads]
            for r in is_cable_roads[1:]:
                line_of[find(r)] = find(is_cable_roads[0])
            if len(is_cable_roads) == 1:
                line_ends.add(is_cable_roads[0])
        lines = {}
        for rd_id in cable_roads:
            lines.setdefault(find(rd_id), []).append(rd_id)
        for line in lines.values():
            if not any(rd_id in line_ends for rd_id in line):
                names = ', '.join(cable_roads[rd_id].get("original_name", rd_id) for rd_id in line)
                report.warning("the cable car line of " + names + " has no ends, MM2 puts a cable car only at each end"
                      + " of a line (an intersection where only one cable car road arrives), so it will have no cable cars")

    def get_flags(self, rd, zs):
        rd_pr = self.prop(rd)
        flags = 0
        if rd_pr.get("divided", "0") == "1":
            flags |= FLAG_DIVIDED
        if rd_pr.get("alley", "0") == "1":
            flags |= FLAG_ALLEY
        if rd_pr.get("freeway", "0") == "1":
            flags |= FLAG_FREEWAY
        if all(abs(float(np.dot(z, UP))) < 1e-3 for z in zs):
            flags |= FLAG_FLAT
        return flags

    def get_automatically_placed_traffic_light(self, index_in_intersection, intersection_roads, block_id, road_properties, road, end_index):
        # Automatic traffic lights placement
        # They are placed on the opposite road (as in MM2)
        # (it actually uses the road with index+2, so only
        # for intersections with 4 roads it's the opposite.
        # It also excludes roads without traffic from the count.)

        # Find the opposite road
        if not intersection_roads:
            report.warning("no roads available for automatic traffic light placement")
            return (np.zeros(3), np.zeros(3))
        road_2_properties = None
        for step in range(len(intersection_roads)):
            opposite_road_index = (index_in_intersection + 2 + step) % len(intersection_roads)
            road_id = intersection_roads[opposite_road_index]
            road_2 = next((r for r in self.roads_finished if self.prop(r)["id"] == road_id), None)
            if road_2 is None:
                continue
            candidate = self.prop(road_2)
            if int(candidate["traffic_type"]) == 3 and (candidate["left_lanes"] == "0" or candidate["right_lanes"] == "0"):
                continue
            road_2_properties = candidate
            break
        if road_2_properties is None:
            report.warning("no traffic road available for automatic traffic light placement")
            return (np.zeros(3), np.zeros(3))

        # Place the traffic light, near the curb of the opposite road, on the side of the lanes leaving the intersection
        geo_2 = self.geometries[road_2_properties["id"]]
        geo = self.geometries[road_properties["id"]]
        light_dir = 1 if road_2_properties["end_intersection"] == block_id else 0
        if light_dir == 1:
            vo1 = geo_2.right_curb[-1]
            vo2 = geo_2.right_outer[-1]
        else:
            vo1 = geo_2.left_curb[0]
            vo2 = geo_2.left_outer[0]
        vo = np.divide(np.add(np.multiply(vo1, 3), vo2), 4)
        if end_index == 0:
            oA = geo.left_outer[0]
            oB = geo.right_outer[0]
        else:
            oA = geo.right_outer[-1]
            oB = geo.left_outer[-1]
        vd0 = self.vector_projection(oA, oB, vo)
        vd = self.rotate_point(vd0, vo, np.deg2rad(90.0))
        return (vo, vd)

    def bai_intersection_roads(self, intersection):
        # the ids of the roads of an intersection that are in the BAI (roads without traffic aren't), in order:
        # the road list written for the intersection and the index of a road in it (its road ends) use this list
        finished_ids = {self.prop(r)["id"] for r in self.roads_finished}
        return [crs for crs in self.prop(intersection)["roads"].split(";") if crs in finished_ids]

    def write_road_end(self, road, end_index):
        road_properties = self.prop(road)
        file = self.file
        road_intersections = [road_properties["start_intersection"], road_properties["end_intersection"]]
        road_rules = [road_properties["start_rule"], road_properties["end_rule"]]
        index_in_intersection = -1
        intersection_index = CDCDCDCD
        this_road_id = road_properties["id"]
        block_id = road_intersections[end_index]
        if block_id == "0":
            # disconnected road
            road_rule = "2"
            index_in_intersection = CDCDCDCD
        else:
            road_rule = road_rules[end_index]

            # Find the intersection
            intersection = None
            for i in range(len(self.intersections_finished)):
                temp_intersection = self.intersections_finished[i]
                if block_id == self.prop(temp_intersection)["block"]:
                    intersection = temp_intersection
                    intersection_index = i
            intersection_roads = self.bai_intersection_roads(intersection)

            # Find the index of this road in the intersection
            for i in range(len(intersection_roads)):
                if intersection_roads[i] == this_road_id:
                    index_in_intersection = i

        # Write the road end
        file.write_uint32(intersection_index)
        file.write_uint16(52685)  # cdcd
        file.write_uint32(int(road_rule))
        file.write_uint32(index_in_intersection)

        if road_rules[end_index] == "1" and block_id != "0":
            tl_key = this_road_id + "." + str(end_index)
            if tl_key in self.traffic_lights:
                # Manually placed traffic light
                traffic_light = self.traffic_lights[tl_key]
                vo = self.scene_input.get_position(traffic_light)
                rot = self.scene_input.get_rotation(traffic_light)
                vd0 = [vo[0] - 1.0, vo[1], vo[2]]
                vd = self.rotate_point(vd0, vo, rot[2])
            else:
                (vo, vd) = self.get_automatically_placed_traffic_light(index_in_intersection, intersection_roads, block_id, road_properties, road, end_index)
            # the axis is a point 1 m from the light
            vd = np.add(vo, normalized(np.subtract(vd, vo)))
            file.write_vec3(vo)
            file.write_vec3(vd)
        else:
            # Empty data for (unused) traffic lights
            for i in range(6):
                file.write_float(0.0)

    def get_traffic_type(self, rd, is_right_side):
        rd_pr = self.prop(rd)
        this_side_has_sidewalks = self.get_which_sides_have_sidewawlks(rd_pr["has_sidewalks"])[1 if is_right_side else 0] > 0
        has_geo_sidewalks = int(rd_pr["has_geo_sidewalks"]) > 0
        traffic_type = int(rd_pr["traffic_type"])
        n_right, n_left = self.get_lane_counts(rd)
        n_lanes = n_right if is_right_side else n_left
        if n_lanes == 0:
            if traffic_type == 0 or (traffic_type == 1 and this_side_has_sidewalks):
                traffic_type = 1
            else:
                traffic_type = 3
        elif traffic_type == 0 and ((not this_side_has_sidewalks) or (not has_geo_sidewalks)):
            traffic_type = 2
        return traffic_type

    def write_road_data(self, rd, route, is_right_side):
        file = self.file
        geo = route['geo']
        centre = route['centre']
        n_sections = geo.num_sections()
        # the right side lanes (and rails) are written from the end to the start
        if is_right_side:
            lanes = [list(reversed(lane)) for lane in geo.right_lanes]
            rails = [list(reversed(route['rails'][0]))] if len(route['rails']) > 0 else []
            curb = geo.right_curb
            outer = geo.right_outer
            sidewalk_centre = route['right_sidewalk']
        else:
            lanes = geo.left_lanes
            rails = [route['rails'][1]] if len(route['rails']) > 0 else []
            curb = geo.left_curb
            outer = geo.left_outer
            sidewalk_centre = route['left_sidewalk']

        file.write_uint16(len(lanes))
        file.write_uint16(len(rails))
        file.write_uint16(0)  # trains
        file.write_uint16(1)  # sidewalks
        file.write_uint16(self.get_traffic_type(rd, is_right_side))

        # distances along each lane and along the sidewalk
        for lane in lanes:
            for d in cumulative_lengths(lane):
                file.write_float(d)
        for d in cumulative_lengths(sidewalk_centre):
            file.write_float(d)

        # distances of the lanes (inner first) and of the sidewalk from the centre line, then the lane boundaries
        first_points = [lane[-1] if is_right_side else lane[0] for lane in lanes] + [sidewalk_centre[0]]
        offsets = lateral_offsets(first_points, centre[0], route['x'][0])
        for d in offsets:
            file.write_float(d)
        for d in lane_boundaries(offsets, route['half_width']):
            file.write_float(d)

        for lane in lanes:
            for v in lane:
                file.write_vec3(v)
        for v in sidewalk_centre:
            file.write_vec3(v)
        for rail in rails:
            for v in rail:
                file.write_vec3(v)
        for v in curb:
            file.write_vec3(v)
        for v in outer:
            file.write_vec3(v)

    def get_bounding_box(self, vertices, add):
        # Returns the bounding box for a set of vertices,
        # with its size increased in each direction by the "add" value
        min_x = float('inf')
        min_y = float('inf')
        min_z = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')
        max_z = float('-inf')
        for v in vertices:
            if v[0] > max_x:
                max_x = v[0]
            if v[0] < min_x:
                min_x = v[0]
            if v[1] > max_y:
                max_y = v[1]
            if v[1] < min_y:
                min_y = v[1]
            if v[2] > max_z:
                max_z = v[2]
            if v[2] < min_z:
                min_z = v[2]
        return [[min_x - add, min_y - add, min_z - add], [max_x + add, max_y + add, max_z + add]]

    def boxes_intersect(self, b1, b2):
        ai = [(b2[0][a] > b1[1][a] or b2[1][a] < b1[0][a]) for a in range(3)]
        return not (ai[0] or ai[1] or ai[2])

    def collect_objects(self):
        # the BAI roads and intersections, and the traffic lights; returns the number of roads and intersections
        self.roads_finished = []
        self.intersections_finished = []
        self.traffic_lights = {}
        print("Getting the BAI objects...")
        obj_count = 0
        for o in self.scene_input.get_object_list():
            o_pr = self.scene_input.get_property_container(o)
            obj_type = self.utils.get_object_type(o)
            if obj_type == "BAI":
                if bool(int(o_pr["is_road"])):
                    self.roads_finished.append(o)
                else:
                    self.intersections_finished.append(o)
                obj_count += 1.0
            elif obj_type == "TRAFL":
                tl_key = o_pr["road_id"] + "." + ("0" if o_pr["is_start_intersection_light"] == "1" else "1")
                self.traffic_lights[tl_key] = o
        return obj_count

    def get_cable_car_rails(self):
        # the rails of the cable car roads with rail decals (as in the BAI), and the curves joining them through the
        # intersections where a line goes from a road into another one: [(polyline, road properties)]
        self.collect_objects()
        routes = {}
        res = []
        for rd in self.roads_finished:
            rd_pr = self.prop(rd)
            if rd_pr.get("cable_car", "0") != "1" or "cable_car_rail_decal" not in rd_pr:
                continue
            route = self.get_route(rd)
            routes[rd_pr["id"]] = (route, rd_pr)
            for rail in route['rails']:
                res.append((rail, rd_pr))
        for IS in self.intersections_finished:
            centre = self.get_intersection_center(IS)
            ends = []
            for rd_id in self.prop(IS)["roads"].split(";"):
                if rd_id not in routes:
                    continue
                route, rd_pr = routes[rd_id]
                c = route['centre']
                # the end of the road at the intersection, and its direction towards it
                at_end = np.linalg.norm(np.subtract(c[-1], centre)) < np.linalg.norm(np.subtract(c[0], centre))
                idx, prev = (-1, -2) if at_end else (0, 1)
                heading = normalized(np.subtract(c[idx], c[prev]))
                ends.append((heading, [rail[idx] for rail in route['rails']], rd_pr))
            res.extend(self.join_rails(ends))
        return res

    def join_rails(self, ends):
        # pairs the cable car roads of an intersection going into each other (the most opposite directions first), and
        # joins the rails of each pair (each one with the closest one of the other road) with a curve
        res = []
        pairs = sorted((float(np.dot(ends[i][0], ends[j][0])), i, j) for i in range(len(ends)) for j in range(i + 1, len(ends)))
        used = set()
        for dot, i, j in pairs:
            if dot > RAIL_JOIN_MAX_DOT or i in used or j in used:
                continue
            used.update((i, j))
            (h_a, rails_a, rd_pr), (h_b, rails_b, _) = ends[i], ends[j]
            if len(rails_a) != 2 or len(rails_b) != 2:
                continue
            straight = self.verts_distance(rails_a[0], rails_b[0]) + self.verts_distance(rails_a[1], rails_b[1])
            crossed = self.verts_distance(rails_a[0], rails_b[1]) + self.verts_distance(rails_a[1], rails_b[0])
            if crossed < straight:
                rails_b = rails_b[::-1]
            for a, b in zip(rails_a, rails_b):
                length = self.verts_distance(a, b)
                n = max(2, int(math.ceil(length / RAIL_JOIN_STEP)))
                curve = []
                for k in range(n + 1):
                    t = k / n
                    h00, h10, h01, h11 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t, -2*t**3 + 3*t**2, t**3 - t**2
                    curve.append(np.array(a) * h00 + h_a * length * h10 + np.array(b) * h01 - h_b * length * h11)
                res.append((curve, rd_pr))
        return res

    def write(self):
        self.scene_input.init_progress_bar()
        self.file = BinaryFileHelper(self.filepath.replace(".psdl", ".bai"), 'wb')
        file = self.file
        obj_count = self.collect_objects()
        self.warn_cable_car_lines_without_ends()
        self.geometries = {}
        for rd in self.roads_finished:
            self.geometries[self.prop(rd)["id"]] = self.get_route_geometry(rd)
        blocks = self.utils.get_real_blocks()
        blocks_o = []
        for b in blocks:
            blocks_o.append([])
        for obj in self.scene_input.get_object_list():
            iblock = self.utils.get_block_number(obj)
            for i in range(len(blocks)):
                if iblock == blocks[i][0]:
                    blocks_o[i].append(obj)
                    break
        print("writing the bai...")
        file.write_raw_string("CAI1")
        file.write_uint16(len(self.intersections_finished))
        file.write_uint16(len(self.roads_finished))
        progress = 0
        progress2 = 0.0
        for i_rd in range(len(self.roads_finished)):
            rd = self.roads_finished[i_rd]
            rd_pr = self.scene_input.get_property_container(rd)
            rd_blocks = rd_pr["blocks"].split(";")
            route = self.get_route(rd)
            n_sections = route['geo'].num_sections()
            file.write_uint16(i_rd)
            file.write_uint16(n_sections)
            file.write_uint16(route['flags'])
            file.write_uint16(len(rd_blocks))
            for rdb in rd_blocks:
                iblock = int(rdb)
                ib = self.utils.get_real_block_number(blocks, iblock)
                file.write_uint16(ib + 1)
            file.write_float(route['half_width'])
            file.write_float(BASE_SPEED)
            self.write_road_data(rd, route, True)
            self.write_road_data(rd, route, False)
            for d in cumulative_lengths(route['centre']):
                file.write_float(d)
            for a in [route['centre'], route['x'], route['y'], route['z'], route['tangents']]:
                for v in a:
                    file.write_vec3(v)
            self.write_road_end(rd, 1)
            self.write_road_end(rd, 0)
            progress += 1
            progress2 += 1
            print(str(progress))
            if progress2 % 10 == 0:
                self.scene_input.set_progress_bar(0.99 + (progress2/obj_count) * 0.001)
        progress = 0
        for iIS in range(len(self.intersections_finished)):
            IS = self.intersections_finished[iIS]
            IS_p = self.prop(IS)
            is_roads = IS_p["roads"].split(";")
            if len(is_roads) > MAX_INTERSECTION_ROADS:
                report.warning("a BAI intersection has " + str(len(is_roads)) + " roads, more than "
                      + str(MAX_INTERSECTION_ROADS) + ": the ambient traffic of the game crashes on it",
                      element=report.element_name(IS_p.get("original_name")), kind="intersection")
            iblock = int(IS_p["block"])
            ib = self.utils.get_real_block_number(blocks, iblock)
            file.write_uint16(iIS)
            file.write_uint16(ib + 1)
            file.write_vec3(self.get_intersection_center(IS))
            # only the roads that are in the BAI: the count must match the indices written
            road_indices = [ir for crs in self.bai_intersection_roads(IS) for ir in range(len(self.roads_finished))
                            if crs == self.prop(self.roads_finished[ir])["id"]]
            file.write_uint16(len(road_indices))
            for ir in road_indices:
                file.write_uint32(ir)
            progress += 1
            progress2 += 1
            print(str(progress))
            if progress2 % 10 == 0:
                self.scene_input.set_progress_bar(0.99 + (progress2/obj_count) * 0.001)
        file.write_uint32(len(blocks) + 1)
        cull_large_list = []
        cull_small_list = []
        large_bubble_size = 200.0
        small_bubble_size = 100.0
        progress = 0.0
        valid_block_types = ["ROADS", "ROADN", "ROADSN", "ROADD", "ROADDN", "BLOCK", "IS", "NUL"]
        road_bounding_boxes_large = []
        road_bounding_boxes_small = []
        for i2 in range(len(self.roads_finished)):
            r = self.roads_finished[i2]
            road_vertices = []
            num_verts_r = self.scene_input.get_vertices_num(r)
            for i_vr in range(num_verts_r):
                vr = self.scene_input.get_vertex(r, i_vr)
                road_vertices.append(vr)
            road_bounding_boxes_large.append(self.get_bounding_box(road_vertices, large_bubble_size / 2))
            road_bounding_boxes_small.append(self.get_bounding_box(road_vertices, small_bubble_size / 2))
        for i in range(len(blocks)):
            cull_large = []
            cull_small = []
            b = blocks_o[i]
            block_vertices = []
            for obj in b:
                objtyp = self.utils.get_object_type(obj)
                if objtyp in valid_block_types:
                    num_verts_obj = self.scene_input.get_vertices_num(obj)
                    for i_vb in range(num_verts_obj):
                        vb = self.scene_input.get_vertex(obj, i_vb)
                        block_vertices.append(vb)
            bounding_box_large = self.get_bounding_box(block_vertices, large_bubble_size / 2)
            bounding_box_small = self.get_bounding_box(block_vertices, small_bubble_size / 2)
            for i2 in range(len(self.roads_finished)):
                road_box = road_bounding_boxes_large[i2]
                intersect = self.boxes_intersect(bounding_box_large, road_box)
                if not intersect:
                    continue
                if self.accurate_culling:
                    # Accurate culling (slower)
                    # Checks the actual distance for each of the two bubbles
                    r = self.roads_finished[i2]
                    found = False
                    found2 = False
                    for obj in b:
                        if found:
                            break
                        num_verts_obj2 = self.scene_input.get_vertices_num(obj)
                        objtyp = self.utils.get_object_type(obj)
                        if objtyp in valid_block_types:
                            for i_vb in range(num_verts_obj2):
                                if found:
                                    break
                                vb = self.scene_input.get_vertex(obj, i_vb)
                                num_verts_r2 = self.scene_input.get_vertices_num(r)
                                for i_vr in range(num_verts_r2):
                                    if found:
                                        break
                                    vr = self.scene_input.get_vertex(r, i_vr)
                                    dist = self.verts_distance(vb, vr)
                                    if dist < small_bubble_size:
                                        found = True
                                        cull_small.append(i2)
                                        if not found2:
                                            found2 = True
                                            cull_large.append(i2)
                                    elif dist < large_bubble_size and not found2:
                                        found2 = True
                                        cull_large.append(i2)
                else:
                    # Approximate culling (faster)
                    # Only does a bounding box check for the small bubble
                    # (the large one has been checked already)
                    cull_large.append(i2)
                    road_box2 = road_bounding_boxes_small[i2]
                    intersect2 = self.boxes_intersect(bounding_box_small, road_box2)
                    if intersect2:
                        cull_small.append(i2)
            cull_large_list.append(cull_large)
            cull_small_list.append(cull_small)
            progress += 1.0
            print(str(progress))
            if progress % 10 == 0:
                self.scene_input.set_progress_bar(0.991 + (progress/len(blocks))*0.009)
        for cullN in [cull_large_list, cull_small_list]:
            for i in range(-1, len(blocks)):
                if i == -1:
                    file.write_uint16(0)
                else:
                    file.write_uint16(len(cullN[i]))
                    for i2 in range(len(cullN[i])):
                        file.write_uint16(cullN[i][i2])
        file.close()
        self.scene_input.end_progress_bar()
        print("BAI Exported!")
