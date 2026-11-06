# The paths of the BAI on a procedural road, from its start to its end (see model.RoadPaths): the edges and curbs of
# its sections, and the paths drawn in the editor (the traffic lanes of the road type, see RoadGenerator in the
# program), which are used when they fit the road: one point per section, and as many as needed. Otherwise the paths
# are derived from the sections, with a warning.

import numpy as np

from utils import state_val, state_bool, state_int
from writers import report
from .model import BaiSide, RoadPaths

# the types of the traffic lanes of the road types (the "type" of trafficLanes in the core), in the lane names
# (traffic_<type>_<component>_<list index>_<lane index>)
LANE_PEDESTRIANS = 0
LANE_FORWARD = 1
LANE_BACKWARD = 2
LANE_RAILS = (3, 4)
# the editor draws the lanes this much above the road
LANE_DRAW_HEIGHT = 0.01
DEFAULT_CABLE_CAR_OFFSET = 2.5


def lane_counts(state):
    # the traffic lanes of a road (forward, backward)
    if state_bool(state, 'disableTraffic'):
        return 0, 0
    return state_int(state, 'forwardLanes'), state_int(state, 'backwardLanes')


def cable_car_offset(state):
    # the distance of the rails from the centre, as cableCarOffsetI in the road parameters
    offset = float(state_val(state, 'cableCarOffset', 0) or 0)
    return offset if offset > 0 else DEFAULT_CABLE_CAR_OFFSET


def editor_lanes(road):
    # the lanes drawn in the editor by type: {type: [points]}, at the height of the road
    res = {}
    for lane in road['data']['fields'].get('lanes', []):
        name = lane['name']
        if not name.startswith('traffic_'):
            continue
        typ = int(name.split('_')[1])
        res.setdefault(typ, []).append([np.subtract(p, (0, LANE_DRAW_HEIGHT, 0)) for p in lane['points']])
    return res


def paths_from_sections(sections, n_backward, n_forward):
    # the sides from sections of the BAI (see RoadPaths.section): right outer edge, right curb, the backward lanes and
    # the forward lanes from the right to the left, left curb, left outer edge
    right = BaiSide([s[0] for s in sections], [s[1] for s in sections],
                    [[s[1 + n_backward - k] for s in sections] for k in range(n_backward)])
    left = BaiSide([s[-1] for s in sections], [s[-2] for s in sections],
                   [[s[2 + n_backward + k] for s in sections] for k in range(n_forward)])
    return RoadPaths(right, left)


class RoadPathsBuilder:
    def __init__(self, jp):
        self.jp = jp

    def build(self, rec):
        # the paths of an exported road (rec: see JsonProcessor.exported_roads), None if it has less than 2 sections
        base = rec['bai_sections']
        if len(base) < 2:
            return None
        road = rec['road']
        name = road['data']['name']
        state = road['data']['fields']['state']
        has_geo_sidewalks = self.jp.road_has_sidewalks(state, road['data']['fields']['runtimeState'])
        curbs = [(s[1] if has_geo_sidewalks else s[0], s[-2] if has_geo_sidewalks else s[-1]) for s in base]
        f_lanes, b_lanes = lane_counts(state)
        drawn = editor_lanes(road)
        n = len(base)

        # across the road, from the right to the left
        right_dir = np.subtract(base[0][-1], base[0][0])

        def lateral(points):
            return float(np.dot(np.subtract(points[0], base[0][0]), right_dir))
        middle = float(np.dot(right_dir, right_dir)) / 2

        def fitting(typ):
            return [p for p in drawn.get(typ, []) if len(p) == n]

        forward = fitting(LANE_FORWARD)
        backward = fitting(LANE_BACKWARD)
        if len(forward) != f_lanes or len(backward) != b_lanes or len(drawn.get(LANE_FORWARD, [])) != f_lanes or len(drawn.get(LANE_BACKWARD, [])) != b_lanes:
            if f_lanes + b_lanes > 0 and not state_bool(state, 'pedestrianStreet'):
                report.warning('the traffic lanes of ' + name + ' are not as in the editor in the BAI', element=name, kind='road')
            forward, backward = self.spread_lanes(state, base, curbs, f_lanes, b_lanes, has_geo_sidewalks)
        lanes = sorted(backward, key=lateral) + sorted(forward, key=lateral)
        sections = [[base[i][0], curbs[i][0]] + [lane[i] for lane in lanes] + [curbs[i][1], base[i][-1]] for i in range(n)]
        paths = paths_from_sections(sections, b_lanes, f_lanes)

        # the pedestrians (on the right side of the BAI: the left one of the road in the program, see the sections);
        # without sidewalks they walk on the edges of the road, midway between the curb and the outer edge
        sidewalks = fitting(LANE_PEDESTRIANS)
        right = [p for p in sidewalks if lateral(p) < middle]
        left = [p for p in sidewalks if lateral(p) >= middle]
        for side, found, peds in ((paths.right, right, not state_bool(state, 'disableLeftPedestrians')),
                                  (paths.left, left, not state_bool(state, 'disableRightPedestrians'))):
            if len(found) == 1:
                side.sidewalk = found[0]
            elif len(found) > 1 or (peds and has_geo_sidewalks):
                report.warning('the pedestrian paths of ' + name + ' are not as in the editor in the BAI', element=name, kind='road')

        if state_bool(state, 'cableCarLine'):
            rails = [p for typ in LANE_RAILS for p in fitting(typ)]
            right = [p for p in rails if lateral(p) < middle]
            left = [p for p in rails if lateral(p) >= middle]
            if len(right) == 1 and len(left) == 1:
                paths.right.rail, paths.left.rail = right[0], left[0]
            else:
                report.warning('the cable car rails of ' + name + ' are not as in the editor in the BAI', element=name, kind='road')
        return paths

    def spread_lanes(self, state, base, curbs, f_lanes, b_lanes, has_geo_sidewalks):
        # lanes spread evenly between the curbs (or the curbs and the divider): forward, backward
        divided = self.jp.road_has_divider(state) and len(base[0]) >= (6 if has_geo_sidewalks else 4)
        forward = [[] for _ in range(f_lanes)]
        backward = [[] for _ in range(b_lanes)]
        for s, (rc, lc) in zip(base, curbs):
            if divided:
                r_inner = s[2] if has_geo_sidewalks else s[1]
                l_inner = s[3] if has_geo_sidewalks else s[2]
            else:
                mid = np.divide(np.add(rc, lc), 2)
                r_inner = mid if f_lanes > 0 else lc
                l_inner = mid if b_lanes > 0 else rc
            for k in range(b_lanes):
                backward[k].append(np.add(r_inner, np.multiply(np.subtract(rc, r_inner), (k + 0.5) / b_lanes)))
            for k in range(f_lanes):
                forward[k].append(np.add(l_inner, np.multiply(np.subtract(lc, l_inner), (k + 0.5) / f_lanes)))
        return forward, backward
