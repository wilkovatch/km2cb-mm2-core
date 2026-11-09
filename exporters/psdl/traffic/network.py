# The BAI of the city (model.BaiNetwork) from the roads and intersections exported by json_processor.py.
#
# Seamless intersections: two roads joined without a surface between them. Roads with the same section and lanes joined
# this way are a single BAI road through the rooms of all of them (a chain), other ones get a two-road intersection
# sharing the room of one of the roads, where vehicles never stop.
#
# Intersections with more BAI roads than MM2 can handle (see MAX_INTERSECTION_ROADS in the BAI writer) become a ring of
# smaller BAI intersections in the same room, each with a few of the roads, joined by two-way roads only for the cars
# (along an arc around the centre, where they never stop). All of them are in the room of the intersection, so the
# game finds the first one there, as it looks up the intersections of a room before its roads.

import math

import numpy as np

from utils import state_bool, state_int
from writers import report
from writers.bai_writer import MAX_INTERSECTION_ROADS
from .model import BaiNetwork, BaiRoad, BaiIntersection
from .paths import RoadPathsBuilder, lane_counts, cable_car_offset, paths_from_sections

# the ring of BAI intersections replacing an intersection with too many roads (see split_intersection): roads per
# intersection of the ring (with the two ring roads, at most 5 as in the stock cities), ring radius (fraction of the mean
# distance of the road ends from the centre), lanes per side and lane width of the ring roads, distance of the ring roads
# from the intersections, distance between their sections
SPLIT_GROUP_ROADS = 3
SPLIT_RING_RADIUS = 0.65
SPLIT_RING_LANES = 2
SPLIT_RING_LANE_WIDTH = 3.5
SPLIT_RING_END_DISTANCE = 8.0
SPLIT_RING_STEP = 5.0
# as the vertices merged by the PSDL writer
SEAMLESS_EPSILON = 0.03

RULE_NEVER_STOP = 3


def is_seamless(intersection):
    instance_state = intersection['data']['fields']['instanceState']
    roads = intersection['roads']
    return state_bool(instance_state, 'seamless') and len(roads) == 2 and roads[0] != roads[1]


def surface_height(elem, x, z, default):
    # the height of the highest triangle of a mesh at (x, z), default if there is none (or no mesh: an intersection
    # without geometry)
    if elem is None or len(elem.indices) < 3:
        return default
    v = np.array(elem.vertices, dtype=float)
    tri = np.array(elem.indices).reshape(-1, 3)
    a, b, c = v[tri[:, 0]], v[tri[:, 1]], v[tri[:, 2]]
    d = (b[:, 2] - c[:, 2]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 2] - c[:, 2])
    ok = np.abs(d) > 1e-9
    d = np.where(ok, d, 1.0)
    l1 = ((b[:, 2] - c[:, 2]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (z - c[:, 2])) / d
    l2 = ((c[:, 2] - a[:, 2]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (z - c[:, 2])) / d
    l3 = 1 - l1 - l2
    inside = ok & (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
    if not np.any(inside):
        return default
    return float(np.max((l1 * a[:, 1] + l2 * b[:, 1] + l3 * c[:, 1])[inside]))


class BaiNetworkBuilder:
    # records: the exported roads, {road id: {'road': road, 'block': its room, 'rooms': all its rooms (a road without
    # geometry, in the rooms it lies over), 'bai_sections': the sections of its mesh used by the BAI}}; intersections: the
    # exported intersections, [(surface part (None without geometry), intersection, its room)]
    def __init__(self, data, records, intersections, road_has_sidewalks, road_has_divider):
        self.data = data
        self.records = records
        self.intersections = intersections
        self.road_has_sidewalks = road_has_sidewalks
        self.road_has_divider = road_has_divider
        self.path_builder = RoadPathsBuilder(self)
        self.path_cache = {}
        self.chains = []  # the BAI roads of the procedural roads: [(road id, reversed)]
        self.road_map = {}  # road id -> its chain
        self.network = BaiNetwork()

    # Roads

    def road_name(self, road_id):
        return self.data['roads'][road_id]['data']['name']

    def paths(self, road_id, reverse=False):
        # the paths of an exported road (as seen going from its end to its start if reversed), None without traffic geometry
        if road_id not in self.path_cache:
            rec = self.records.get(road_id)
            self.path_cache[road_id] = self.path_builder.build(rec) if rec is not None else None
        paths = self.path_cache[road_id]
        return paths.reversed() if paths is not None and reverse else paths

    def layout(self, road_id, reverse):
        # the lanes and ambients of an exported road, as seen going from its end to its start if reversed
        road = self.records[road_id]['road']
        r_state = road['data']['fields']['state']
        r_rt_state = road['data']['fields']['runtimeState']
        left_ped = not state_bool(r_state, 'disableLeftPedestrians')
        right_ped = not state_bool(r_state, 'disableRightPedestrians')
        f_lanes, b_lanes = lane_counts(r_state)
        with_peds = left_ped or right_ped
        with_traffic = (b_lanes > 0 or f_lanes > 0) and not state_bool(r_state, 'pedestrianStreet')
        traffic_type = 0 if with_peds and with_traffic else (1 if with_peds else (2 if with_traffic else 3))
        if reverse:
            f_lanes, b_lanes = b_lanes, f_lanes
            left_ped, right_ped = right_ped, left_ped
        paths = self.paths(road_id, reverse)
        return {
            'forward_lanes': f_lanes,
            'backward_lanes': b_lanes,
            'left_ped': left_ped,
            'right_ped': right_ped,
            'traffic_type': traffic_type,
            'has_geo_sidewalks': bool(self.road_has_sidewalks(r_state, r_rt_state)),
            'vps': len(paths.section(0)) if paths is not None else 0,
            'cable_car': state_bool(r_state, 'cableCarLine'),
            'cable_car_offset': cable_car_offset(r_state)
        }

    def rooms(self, road_id):
        # the rooms of an exported road: its own, or the ones it lies over without geometry
        rec = self.records[road_id]
        return rec.get('rooms') or [rec['block']]

    def has_bai_geometry(self, road_id):
        return road_id in self.records and self.paths(road_id) is not None

    def are_seamless_roads_compatible(self, intersection):
        # same layout and the same section at the joint, going from the first road into the second one
        r0, r1 = intersection['roads']
        if not self.has_bai_geometry(r0) or not self.has_bai_geometry(r1):
            return False
        rev0 = self.records[r0]['road']['startIntersectionId'] == intersection['id']
        rev1 = self.records[r1]['road']['endIntersectionId'] == intersection['id']
        if self.layout(r0, rev0) != self.layout(r1, rev1):
            return False
        p0 = self.paths(r0, rev0)
        sec0 = p0.section(p0.num_sections() - 1)
        sec1 = self.paths(r1, rev1).section(0)
        return all(np.linalg.norm(np.subtract(a, b)) < SEAMLESS_EPSILON for a, b in zip(sec0, sec1))

    def far_intersection(self, road_id, reverse):
        road = self.records[road_id]['road']
        return road['startIntersectionId'] if reverse else road['endIntersectionId']

    def near_intersection(self, road_id, reverse):
        return self.far_intersection(road_id, not reverse)

    def get_chains(self, compatible_joints):
        # the roads in a row through compatible seamless joints, as (road id, reversed)
        visited = set()
        chains = []

        def walk(road_id, reverse):
            chain = []
            while road_id not in visited:
                visited.add(road_id)
                chain.append((road_id, reverse))
                far = self.far_intersection(road_id, reverse)
                if far not in compatible_joints:
                    break
                r0, r1 = compatible_joints[far]['roads']
                road_id = r1 if road_id == r0 else r0
                reverse = self.records[road_id]['road']['endIntersectionId'] == far
            return chain

        for road_id in self.records:
            if road_id in visited:
                continue
            road = self.records[road_id]['road']
            if road['startIntersectionId'] not in compatible_joints:
                chains.append(walk(road_id, False))
            elif road['endIntersectionId'] not in compatible_joints:
                chains.append(walk(road_id, True))

        looped = [road_id for road_id in self.records if road_id not in visited]
        if len(looped) > 0:
            names = ', '.join(self.road_name(r) for r in looped)
            report.warning('the roads ' + names + ' form a loop of seamless intersections without other intersections, no BAI road for them')
        return chains

    def bai_road_end(self, road_id, at_road_start):
        # the end of the BAI road (0: start, 1: end) on the start or end of a road, None if it isn't one
        if road_id not in self.road_map:
            return None
        chain = self.chains[self.road_map[road_id]]
        first_id, first_rev = chain[0]
        last_id, last_rev = chain[-1]
        if road_id == first_id and at_road_start != first_rev:
            return 0
        if road_id == last_id and at_road_start == last_rev:
            return 1
        return None

    def chain_road(self, chain):
        # the BAI road of a chain of roads (its ends are set later)
        first_id, first_rev = chain[0]
        layout = self.layout(first_id, first_rev)
        names = ', '.join(self.road_name(road_id) for road_id, _ in chain)
        if layout['vps'] == 0:
            raise Exception('Invalid road while exporting traffic info on road: ' + names)
        paths = None
        rooms = []
        for road_id, reverse in chain:
            p = self.paths(road_id, reverse)
            paths = p if paths is None else paths.joined(p)
            for block in self.rooms(road_id):
                if block not in rooms:
                    rooms.append(block)
        r_state = self.records[first_id]['road']['data']['fields']['state']
        road = BaiRoad(names, rooms, paths)
        # the right side of the BAI is the left one of the road in the program (see paths.py)
        road.pedestrians = (layout['left_ped'], layout['right_ped'])
        road.traffic_type = layout['traffic_type']
        road.geo_sidewalks = layout['has_geo_sidewalks']
        road.divided = bool(self.road_has_divider(r_state))
        road.freeway = state_bool(r_state, 'freeway')
        road.alley = state_bool(r_state, 'pedestrianStreet')
        road.cable_car = layout['cable_car']
        road.cable_car_offset = layout['cable_car_offset']
        return road

    def chain_rules(self, chain, road):
        # the rules of the ends of the BAI road of a chain (an end without lanes towards it has rule 0)
        first_id, first_rev = chain[0]
        last_id, last_rev = chain[-1]
        first_inst_state = self.records[first_id]['road']['data']['fields']['instanceState']
        last_inst_state = self.records[last_id]['road']['data']['fields']['instanceState']
        b_lanes = len(road.paths.right.lanes)
        f_lanes = len(road.paths.left.lanes)
        road.start.rule = int(state_int(first_inst_state, 'end_rule' if first_rev else 'start_rule')) if b_lanes > 0 else 0
        road.end.rule = int(state_int(last_inst_state, 'start_rule' if last_rev else 'end_rule')) if f_lanes > 0 else 0
        if self.near_intersection(first_id, first_rev) in self.seamless_joint_ids and b_lanes > 0:
            road.start.rule = RULE_NEVER_STOP
        if self.far_intersection(last_id, last_rev) in self.seamless_joint_ids and f_lanes > 0:
            road.end.rule = RULE_NEVER_STOP

    def single_road(self, road_id):
        # the BAI road of a single road, without its intersections (for the converters), None without traffic geometry
        if not self.has_bai_geometry(road_id):
            return None
        return self.chain_road([(road_id, False)])

    # Intersections

    def seamless_joint_intersection(self, intersection, used_blocks):
        # a two-road intersection in the room of one of the roads, or the reason why it can't be made
        for road_id in intersection['roads']:
            if not self.has_bai_geometry(road_id):
                return (None, 'the road ' + self.road_name(road_id) + ' is not exported or has no traffic geometry')
        for road_id in intersection['roads']:
            # the room of the road at the joint (the last one at its end, for a road exported as several rooms)
            rooms = self.rooms(road_id)
            at_end = self.records[road_id]['road']['endIntersectionId'] == intersection['id']
            block = rooms[-1] if at_end else rooms[0]
            if block not in used_blocks:
                return ((None, intersection, block), None)
        return (None, 'the rooms of both roads are already used by other intersections')

    def entries(self, intersection):
        # the road ends on an intersection, counterclockwise (in the generator the roads are clockwise), as (road id,
        # at road start)
        order = intersection['data']['fields']['sortOrder']
        res = []
        for i in range(len(intersection['roads'])):
            road_id = intersection['roads'][order[-1 - i]]
            if road_id not in self.road_map:
                continue
            road = self.data['roads'][road_id]
            at_start = road['startIntersectionId'] == intersection['id']
            if at_start and road['endIntersectionId'] == intersection['id'] and (road_id, True) in res:
                at_start = False  # a road with both ends here: the start is the first one
            res.append((road_id, at_start))
        return res

    def end_section(self, road_id, at_start):
        paths = self.paths(road_id)
        return paths.section(0 if at_start else paths.num_sections() - 1)

    def split_intersection(self, obj, entries):
        # the ring of BAI intersections replacing an intersection with too many roads (None if it isn't needed): the
        # intersection of each road end, the intersections and the roads of the ring
        surface, intersection, block = obj
        n = len(entries)
        if n <= MAX_INTERSECTION_ROADS:
            return None
        name = intersection['data']['name']
        centre = np.array(intersection['center'], dtype=float)
        ends = []
        for road_id, at_start in entries:
            section = self.end_section(road_id, at_start)
            ends.append(np.divide(np.add(section[0], section[-1]), 2))
        angles = [math.atan2(p[2] - centre[2], p[0] - centre[0]) for p in ends]

        # the direction of the order around the centre, and the angle after each road end
        def wrap(a):
            return (a + math.pi) % (2 * math.pi) - math.pi
        sign = 1 if sum(wrap(angles[(i + 1) % n] - angles[i]) for i in range(n)) > 0 else -1
        gaps = [((angles[(i + 1) % n] - angles[i]) * sign) % (2 * math.pi) for i in range(n)]

        # groups of consecutive roads, cut at the widest gaps
        k = int(math.ceil(n / SPLIT_GROUP_ROADS))
        sizes = [n // k + (1 if g < n % k else 0) for g in range(k)]
        best = None
        for first in range(n):
            last = first - 1
            cuts = []
            for size in sizes:
                last += size
                cuts.append(gaps[last % n])
            if best is None or min(cuts) > best[0]:
                best = (min(cuts), first)
        groups = []
        first = best[1]
        for size in sizes:
            groups.append([(first + m) % n for m in range(size)])
            first += size

        # the intersections of the ring, near their roads
        radius = SPLIT_RING_RADIUS * float(np.mean([math.hypot(p[0] - centre[0], p[2] - centre[2]) for p in ends]))
        nodes = []
        node_angles = []
        for g, group in enumerate(groups):
            a = math.atan2(sum(math.sin(angles[i]) for i in group), sum(math.cos(angles[i]) for i in group))
            x = centre[0] + radius * math.cos(a)
            z = centre[2] + radius * math.sin(a)
            y = surface_height(surface, x, z, float(np.mean([ends[i][1] for i in group])))
            node_angles.append(a)
            nodes.append(BaiIntersection(name + ' [BAI ' + str(g + 1) + '/' + str(k) + ']', block, np.array((x, y, z))))

        # the roads of the ring, from each intersection to the next one
        ring = []
        for g in range(k):
            g1 = (g + 1) % k
            delta = ((node_angles[g1] - node_angles[g]) * sign) % (2 * math.pi)
            margin = min(SPLIT_RING_END_DISTANCE, radius * delta / 4) / radius
            steps = max(2, int(math.ceil(radius * (delta - 2 * margin) / SPLIT_RING_STEP)))
            points = []
            directions = []
            for t in range(steps + 1):
                u = t / steps
                a = node_angles[g] + sign * (margin + (delta - 2 * margin) * u)
                x = centre[0] + radius * math.cos(a)
                z = centre[2] + radius * math.sin(a)
                y0 = nodes[g].centre[1] + (nodes[g1].centre[1] - nodes[g].centre[1]) * u
                points.append(np.array((x, surface_height(surface, x, z, y0), z)))
                directions.append(np.multiply((-math.sin(a), 0.0, math.cos(a)), sign))
            road = self.ring_road(name + ' [BAI ring ' + str(g + 1) + '-' + str(g1 + 1) + ']', block, points, directions)
            road.start.intersection, road.end.intersection = nodes[g], nodes[g1]
            ring.append(road)

        # each intersection: its roads in the same order, then the ring road to the next one and the one from the previous one
        end_nodes = {}
        for g in range(k):
            for i in groups[g]:
                end_nodes[entries[i]] = nodes[g]
        print('The BAI intersection of ' + name + ' has ' + str(n) + ' roads (MM2 crashes with more than '
              + str(MAX_INTERSECTION_ROADS) + '), split into a ring of ' + str(k))
        return {'groups': groups, 'nodes': nodes, 'ring': ring, 'ends': end_nodes}

    def ring_road(self, name, block, points, directions):
        # a two-way BAI road through the points, without sidewalks, where the cars never stop
        lanes = SPLIT_RING_LANES
        width = SPLIT_RING_LANE_WIDTH
        offsets = [lanes * width] * 2 + [lanes * width - (k + 0.5) * width for k in range(lanes)]
        offsets += [-(k + 0.5) * width for k in range(lanes)] + [-lanes * width] * 2
        sections = []
        for p, d in zip(points, directions):
            right = np.array((-d[2], 0.0, d[0])) / np.linalg.norm((d[0], d[2]))  # as the roads, see paths.py
            sections.append([np.add(p, np.multiply(right, o)) for o in offsets])
        road = BaiRoad(name, [block], paths_from_sections(sections, lanes, lanes))
        road.pedestrians = (False, False)
        road.traffic_type = 2
        road.geo_sidewalks = False
        road.start.rule = RULE_NEVER_STOP
        road.end.rule = RULE_NEVER_STOP
        return road

    # The network

    def build(self):
        network = self.network
        intersections = list(self.intersections)

        # the roads joined by seamless intersections
        compatible_joints = {}
        incompatible_joints = []
        for intersection in self.data['intersections']:
            if is_seamless(intersection):
                if self.are_seamless_roads_compatible(intersection):
                    compatible_joints[intersection['id']] = intersection
                else:
                    incompatible_joints.append(intersection)

        # two-road intersections at the other ones, in rooms not used by other intersections
        used_blocks = set(obj[2] for obj in intersections)
        joint_intersections = {}
        failed_joints = {}
        for intersection in incompatible_joints:
            (obj, reason) = self.seamless_joint_intersection(intersection, used_blocks)
            if obj is None:
                failed_joints[intersection['id']] = (intersection, reason)
            else:
                joint_intersections[intersection['id']] = obj
                used_blocks.add(obj[2])
        self.seamless_joint_ids = set(joint_intersections.keys())

        # a BAI road for each row of roads with intersections at both ends
        bai_intersections = set(obj[1]['id'] for obj in intersections) | self.seamless_joint_ids
        for chain in self.get_chains(compatible_joints):
            ends = [self.near_intersection(*chain[0]), self.far_intersection(*chain[-1])]
            if all(end in bai_intersections for end in ends):
                self.chains.append(chain)
            else:
                for end in ends:
                    if end in failed_joints:
                        names = ', '.join(self.road_name(road_id) for road_id, _ in chain)
                        (joint, reason) = failed_joints[end]
                        report.warning('no BAI road for ' + names + ': it ends on the seamless intersection ' + joint['data']['name']
                                       + ', which can\'t be a BAI intersection (' + reason + ')',
                                       element=joint['data']['name'], kind='intersection')

        # the two-road intersections without roads are left out
        used_joints = set()
        for chain in self.chains:
            used_joints.add(self.near_intersection(*chain[0]))
            used_joints.add(self.far_intersection(*chain[-1]))
        for intersection_id, obj in joint_intersections.items():
            if intersection_id in used_joints:
                intersections.append(obj)
        self.seamless_joint_ids &= used_joints

        # the roads
        for i, chain in enumerate(self.chains):
            road = network.add_road(self.chain_road(chain))
            self.chain_rules(chain, road)
            for road_id, _ in chain:
                self.road_map[road_id] = i
                network.road_of[road_id] = road

        # the intersections (the ones with too many roads split into rings of smaller ones, with the ring roads after
        # the other roads)
        by_id = {}
        splits = {}
        for obj in intersections:
            surface, intersection, block = obj
            entries = self.entries(intersection)
            split = self.split_intersection(obj, entries)
            if split is None:
                node = network.add_intersection(BaiIntersection(intersection['data']['name'], block, intersection['center']))
                node.roads = [self.entry_end(e) for e in entries]
                by_id[intersection['id']] = node
            else:
                splits[intersection['id']] = split
                for road in split['ring']:
                    network.add_road(road)
                for g, node in enumerate(split['nodes']):
                    network.add_intersection(node)
                    k = len(split['nodes'])
                    node.roads = [self.entry_end(entries[i]) for i in split['groups'][g]]
                    node.roads += [(split['ring'][g], True), (split['ring'][(g - 1) % k], False)]

        # the intersections of the ends of the roads
        def end_intersection(intersection_id, road_id, at_road_start):
            split = splits.get(intersection_id)
            return split['ends'][(road_id, at_road_start)] if split is not None else by_id.get(intersection_id)
        for chain, road in zip(self.chains, network.roads):
            first_id, first_rev = chain[0]
            last_id, last_rev = chain[-1]
            road.start.intersection = end_intersection(self.near_intersection(first_id, first_rev), first_id, not first_rev)
            road.end.intersection = end_intersection(self.far_intersection(last_id, last_rev), last_id, last_rev)
        return network

    def entry_end(self, entry):
        # the end of the BAI road on a road end: (BaiRoad, at its start)
        road_id, at_road_start = entry
        return (self.network.road_of[road_id], self.bai_road_end(road_id, at_road_start) == 0)

    def attach_traffic_light(self, road_id, at_road_start, position, rotation):
        # a traffic light placed by hand on a road end, for the BAI road ending there; False if no BAI road ends there
        end = self.bai_road_end(road_id, at_road_start) if road_id >= 0 else None
        if end is None:
            return False
        road = self.network.road_of[road_id]
        (road.start if end == 0 else road.end).traffic_light = (position, rotation)
        return True
