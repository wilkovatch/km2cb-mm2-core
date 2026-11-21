"""The sidewalks made straight by the roads become sidewalk overrides of the intersections.

The outer side of an intersection sidewalk was made straight by four flags of the roads
(forceStraight{Left,Right}{Start,End}Sidewalk, removed), and, without a flag, where one of its two roads ended with a
negative size increase (its startIntersectionAdd or endIntersectionAdd plus the sizeIncrease of the intersection, the
selfIntersectingSpline of the junction): the straight outer side is no longer automatic. The sidewalk overrides of the
intersections do the same: one outer segment skipping the crosswalks gives the same outer side. Each such sidewalk gets
that override, keeping the geometry (later changes of the size increases don't straighten or curve it again). The
junction read, for
the sidewalk between a road A and the next road B clockwise (the sidewalk on the left of A and on the right of B, seen
from the roads toward the intersection), the Left flag of A and the Right flag of B, of the end of the road on the
intersection. At the start of a road those are the opposite sides of what the names said, so a flag is moved to the
sidewalk it straightened, not to the one its name gave. A flag had no effect on a convex corner: such sidewalks get no
override, as the negative size increases. The order of the roads and the convex corners are computed as the builder does
(IntersectionGenerator.CalculateVerticesAndCenters and ProcessRoad), from the control points next to the ends of the
roads in place of the first points of their curves.
"""
import copy
import math
import struct
import sys
import MigrationHelper

FLAGS = ('forceStraightLeftStartSidewalk', 'forceStraightRightStartSidewalk',
         'forceStraightLeftEndSidewalk', 'forceStraightRightEndSidewalk')
# the road types without geometry (settings.json geometryless), left out of the intersection surfaces
GEOMETRYLESS = ('bai',)


def flag(road, name):
    # instance specific, but older cities may have them in the state too
    for key in ('instanceState', 'state'):
        source = road.get(key)
        if isinstance(source, dict) and source.get(name):
            return True
    return False


def strip_flags(road):
    for key in ('instanceState', 'state'):
        source = road.get(key)
        if isinstance(source, dict):
            for name in FLAGS:
                source.pop(name, None)


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def size_increase(road, intersection):
    # Road.GetIntersectionAdd plus the size increase of the intersection, as the builder adds them (in single precision)
    state = road.get('state') or {}
    end = 'startIntersectionAdd' if road.get('startIntersectionId') == intersection.get('id') else 'endIntersectionAdd'
    return f32(f32(state.get(end) or 0.0) + f32((intersection.get('state') or {}).get('sizeIncrease') or 0.0))


def direction_to_center(road, intersection_id, center):
    # Intersection.GetDirectionToCenter: from the point next to the end of the road on the intersection, horizontal
    points = road.get('points') or []
    if len(points) < 2:
        return None
    if road.get('startIntersectionId') == intersection_id:
        p = points[1]
    elif road.get('endIntersectionId') == intersection_id:
        p = points[-2]
    else:
        return None
    dx, dz = center['x'] - p['x'], center['z'] - p['z']
    length = math.hypot(dx, dz)
    return (dx / length, dz / length) if length > 0 else (0.0, 0.0)


def left_of(direction):
    # Cross(dir, up), normalized and horizontal
    return (-direction[1], direction[0])


def clockwise_order(directions):
    # GeometryHelper.SortClockwise of the road centers (opposite to their directions to the center)
    def angle(i):
        return math.atan2(-directions[i][1], -directions[i][0])
    order = sorted(range(len(directions)), key=angle, reverse=True)
    while order and order[0] != 0:
        order = order[1:] + order[:1]
    return order


def is_convex(dir_i, dir_j):
    # ProcessRoad: the sign of the distance of road j from the plane along road i (the sizes of the roads are positive)
    left_i, left_j = left_of(dir_i), left_of(dir_j)
    along = left_i[0] * dir_j[0] + left_i[1] * dir_j[1]
    if abs(along) > 1e-6:
        return along > 0
    return left_i[0] * left_j[0] + left_i[1] * left_j[1] > 0


def straightened_sidewalks(intersection, roads_by_id):
    """The indices (in the roads of the intersection) of the first roads of the sidewalks made straight by the flags or
    by a negative size increase."""
    iid = intersection.get('id')
    center = intersection.get('center')
    ids = intersection.get('roads') or []
    roads = [roads_by_id.get(r) for r in ids]
    if center is None or not roads or any(r is None for r in roads):
        return []
    directions = []
    for road in roads:
        d = direction_to_center(road, iid, center)
        directions.append(d if d is not None else (0.0, 0.0))
    geometry = [i for i in clockwise_order(directions)
                if ((roads[i].get('state') or {}).get('type') or 'psdl') not in GEOMETRYLESS]
    res = []
    for k, i in enumerate(geometry):
        j = geometry[(k + 1) % len(geometry)]
        road_a, road_b = roads[i], roads[j]
        a_at_end = road_a.get('endIntersectionId') == iid
        b_at_end = road_b.get('endIntersectionId') == iid
        forced = flag(road_a, 'forceStraightLeftEndSidewalk' if a_at_end else 'forceStraightLeftStartSidewalk') \
            or flag(road_b, 'forceStraightRightEndSidewalk' if b_at_end else 'forceStraightRightStartSidewalk') \
            or size_increase(road_a, intersection) < 0 or size_increase(road_b, intersection) < 0
        if forced and not is_convex(directions[i], directions[j]) and i not in res:
            res.append(i)
    return res


def straighten(intersection, road_index):
    # Intersection.SetSidewalkOverride: one outer segment from road end to road end, the inner ones kept
    instance = intersection.setdefault('instanceState', {})
    if not isinstance(instance, dict):
        instance = intersection['instanceState'] = {}
    sidewalks = [s for s in instance.get('sidewalks') or [] if isinstance(s, dict)]
    entry = next((s for s in sidewalks if s.get('road', -1) == road_index), None)
    if entry is None:
        entry = dict(road=road_index, innerSegments=(intersection.get('state') or {}).get('sidewalkSegments', 1))
        sidewalks.append(entry)
    entry['outerSegments'] = 1
    entry['outerSkipsCrosswalks'] = True
    sidewalks.sort(key=lambda s: s.get('road', -1))
    instance['sidewalks'] = sidewalks


def migrate_city(source):
    data = copy.deepcopy(source)
    roads_by_id = {r.get('id'): r for r in data.get('roads') or []}
    changed = []
    for intersection in data.get('intersections') or []:
        indices = straightened_sidewalks(intersection, roads_by_id)
        for index in indices:
            straighten(intersection, index)
        if indices:
            changed.append(intersection.get('name') or 'Intersection ' + str(intersection.get('id')))
    for road in data.get('roads') or []:
        strip_flags(road)
    return data, changed


def process_folder(helper):
    if helper.get_pref('coreVersion', 0) >= 11:
        return
    city, changed = migrate_city(helper.read_local('city.json.gz', True))
    helper.read_and_backup('city.json.gz', True)
    preferences = helper.read_and_backup('preferences.json', False)
    helper.save(city, 'city.json.gz', True)
    if changed:
        print('intersections with sidewalks made straight by the roads (force straight or negative size increase), now '
              'overridden: ' + ', '.join(changed))
    preferences['coreVersion'] = 11
    helper.save(preferences, 'preferences.json', False)


if __name__ == '__main__' or 'mh' in globals():
    process_folder(MigrationHelper.MigrationHelper(sys.argv[1]))
    print('done 11')
