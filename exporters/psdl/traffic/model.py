# The BAI of the city (the paths of the ambient traffic, of the pedestrians and of the cable cars), as built by
# network.py from the city and written by writers/bai_writer.py. The positions are in the coordinates of the program
# (x, y up, z). See docs/exporter.md in the core.


class BaiSide:
    # A side of a road. The right side has the lanes going from the end of the road to its start, the left side the
    # ones going from its start to its end; every polyline goes from the start to the end, with a point per section.
    def __init__(self, outer, curb, lanes, sidewalk=None, rail=None):
        self.outer = outer  # the outer edge (of the sidewalk, if there is one)
        self.curb = curb  # the inner edge of the sidewalk (the outer edge if there is none)
        self.lanes = lanes  # the traffic lanes, inner first
        self.sidewalk = sidewalk  # the path of the pedestrians (None: midway between the curb and the outer edge)
        self.rail = rail  # the cable car rail (None: at the cable car offset from the centre, if there are cable cars)

    def polylines(self):
        return [self.outer, self.curb] + self.lanes + [p for p in (self.sidewalk, self.rail) if p is not None]

    def reversed(self):
        def rev(p):
            return None if p is None else list(reversed(p))
        return BaiSide(rev(self.outer), rev(self.curb), [rev(lane) for lane in self.lanes], rev(self.sidewalk), rev(self.rail))

    def joined(self, other):
        # this side followed by the one of the next road, which starts with the last section of this one
        def join(a, b):
            return None if a is None or b is None else a + b[1:]
        return BaiSide(join(self.outer, other.outer), join(self.curb, other.curb),
                       [join(a, b) for a, b in zip(self.lanes, other.lanes)],
                       join(self.sidewalk, other.sidewalk), join(self.rail, other.rail))


class RoadPaths:
    def __init__(self, right, left):
        self.right = right
        self.left = left

    def num_sections(self):
        return len(self.right.outer)

    def section(self, i):
        # the points across the road at a section, from the right outer edge to the left one: the right curb, the
        # lanes from the right to the left (the right ones first), the left curb
        r, l = self.right, self.left
        return [r.outer[i], r.curb[i]] + [lane[i] for lane in reversed(r.lanes)] + [lane[i] for lane in l.lanes] + [l.curb[i], l.outer[i]]

    def reversed(self):
        # as seen going from the end to the start
        return RoadPaths(self.left.reversed(), self.right.reversed())

    def joined(self, other):
        return RoadPaths(self.right.joined(other.right), self.left.joined(other.left))


class BaiRoadEnd:
    def __init__(self):
        self.intersection = None  # the BaiIntersection, None for a free end
        self.rule = 0  # what the vehicles do at the end: 0 FIFO, 1 traffic light, 2 stop sign, 3 never stop
        self.traffic_light = None  # a traffic light placed by hand: (position, rotation quaternion (x, y, z, w))


class BaiRoad:
    def __init__(self, name, rooms, paths):
        self.index = -1
        self.name = name
        self.rooms = rooms  # the room (block) numbers of the parts the road goes through
        self.paths = paths  # RoadPaths
        self.pedestrians = (True, True)  # right, left
        self.traffic_type = 0  # 0 cars and pedestrians, 1 pedestrians, 2 cars, 3 nothing
        self.geo_sidewalks = True  # the road has sidewalks (not just paths for the pedestrians on its edges)
        self.divided = False
        self.alley = False
        self.freeway = False
        self.cable_car = False
        self.cable_car_offset = 2.5  # the distance of the rails from the centre
        self.start = BaiRoadEnd()
        self.end = BaiRoadEnd()

    def ends(self):
        return ((self.start, True), (self.end, False))


class BaiIntersection:
    def __init__(self, name, room, centre):
        self.index = -1
        self.name = name
        self.room = room  # the room (block) number
        self.centre = centre
        self.roads = []  # the road ends on it, counterclockwise: (BaiRoad, at its start)

    def position_of(self, road, at_start):
        # the index of a road end in the list of the intersection
        for i, end in enumerate(self.roads):
            if end[0] is road and end[1] == at_start:
                return i
        return -1


class BaiNetwork:
    def __init__(self):
        self.roads = []
        self.intersections = []
        self.road_of = {}  # procedural road id -> the BaiRoad it is part of

    def add_road(self, road):
        road.index = len(self.roads)
        self.roads.append(road)
        return road

    def add_intersection(self, intersection):
        intersection.index = len(self.intersections)
        self.intersections.append(intersection)
        return intersection
