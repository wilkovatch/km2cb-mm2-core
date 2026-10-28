"""Bounded MM2 city readers. Coordinates remain in file space until mapping.

Adapted from psdl-viewer: Copyright (c) 2026 ApanLoon, Dummiesman and Wilhelm Kovatch.
See LICENSE-viewer.txt for the MIT permission notice.
"""
import math
import struct
from pathlib import Path


class FormatError(ValueError):
    pass


class Reader:
    def __init__(self, source, name=None):
        self.name = name or str(source)
        self.data = bytes(source) if isinstance(source, (bytes, bytearray)) else Path(source).read_bytes()
        self.offset = 0

    def take(self, count):
        if count < 0 or count > len(self.data) - self.offset:
            raise FormatError(f'{self.name}: truncated record at {self.offset:#x}')
        result = self.data[self.offset:self.offset + count]
        self.offset += count
        return result

    def values(self, fmt, count=1):
        if count < 0 or count > len(self.data):
            raise FormatError(f'{self.name}: invalid count {count}')
        result = struct.unpack('<' + str(count) + fmt, self.take(struct.calcsize(fmt) * count)) if count else ()
        if fmt == 'f' and any(not math.isfinite(v) for v in result):
            raise FormatError(f'{self.name}: non-finite coordinate at {self.offset:#x}')
        return list(result)

    def u8(self): return self.values('B')[0]
    def u16(self): return self.values('H')[0]
    def u32(self): return self.values('I')[0]
    def f32(self): return self.values('f')[0]
    def vec(self): return self.values('f', 3)
    def vecs(self, count): return [self.vec() for _ in range(count)]
    def text(self, count): return self.take(count).split(b'\0', 1)[0].decode('cp1252').strip()


def attributes(data, name):
    r = Reader(data, name)
    result = []
    while r.offset < len(r.data):
        offset = r.offset
        word = r.u16()
        typ, sub = (word >> 3) & 15, word & 7
        a = dict(type=typ, subtype=sub, offset=offset, last=bool(word & 0x80))
        if typ == 10:
            a['texture'] = r.u16() + 256 * sub - 1
        elif typ in (3, 7, 11):
            if sub != {3: 4, 7: 4, 11: 6}[typ]:
                raise FormatError(f'{name}: unsupported fixed attribute {word:#x}')
            a['values'] = r.values('H', sub - 2)
            a['vertices'] = r.values('H', 2)
        elif typ in (0, 1, 2, 4, 5, 6, 8, 9, 12):
            n = sub or r.u16()
            if typ == 8:
                a['values'] = r.values('H', 2)
            if typ == 12:
                a['height'] = r.u16()
            if typ == 9:
                a['values'] = r.values('H', n)
            else:
                count = {0: 4*n, 1: 2*n, 2: 2*n, 4: n, 5: n+2, 6: n+2, 8: 6*n, 12: n+1}[typ]
                a['vertices'] = r.values('H', count)
        else:
            # There is no defined size for unknown attributes. Never guess where the next starts.
            raise FormatError(f'{name}: unknown attribute {word:#x} at {offset:#x}')
        result.append(a)
    return result


def read_psdl(path):
    r = Reader(path)
    if r.take(4) != b'PSD0':
        raise FormatError(f'{path}: expected PSD0 (PSD1 is unsupported)')
    target = r.u32()
    vertices, heights = r.vecs(r.u32()), r.values('f', r.u32())
    texture_count=r.u32()
    if texture_count<1:raise FormatError(f'{path}: missing null texture entry')
    textures = [r.text(r.u8()) for _ in range(texture_count - 1)]
    count, unknown = r.u32() - 1, r.u32()
    if count<0:raise FormatError(f'{path}: missing null room entry')
    rooms = []
    for i in range(count):
        np, na = r.u32(), r.u32()
        perimeter = [r.values('H', 2) for _ in range(np)]
        attrs = attributes(r.take(2 * na), f'{path}: room {i+1}')
        if any(v >= len(vertices) or neighbor > count for v, neighbor in perimeter):
            raise FormatError(f'{path}: room {i+1}: invalid perimeter reference')
        for a in attrs:
            if any(v >= len(vertices) for v in a.get('vertices', [])):
                raise FormatError(f'{path}: room {i+1}: invalid attribute vertex')
        rooms.append(dict(perimeter=perimeter, attributes=attrs))
    flags, rules = r.values('B', count+1), r.values('B', count+1)
    bounds = r.values('f', 10)
    paths = []
    for _ in range(r.u32()):
        flags0 = r.u32()
        nf, nb = r.u8(), r.u8()
        forward, backward = r.values('f', nf), r.values('f', nb)
        unknown6 = r.u16()
        cross = r.values('H', 8)
        path_rooms = r.values('h', r.u8())
        if any(not 1 <= abs(i) <= count for i in path_rooms):
            raise FormatError(f'{path}: invalid prop path room')
        paths.append(dict(flags=flags0, forward=forward, backward=backward, unknown=unknown6, negativeRooms=any(i<0 for i in path_rooms),
                          cross=cross, rooms=[abs(i) for i in path_rooms]))
    for i, room in enumerate(rooms, 1):
        room.update(flags=flags[i], propRule=rules[i])
    return dict(vertices=vertices, heights=heights, textures=textures, rooms=rooms, paths=paths,
                target=target, unknown=unknown, bounds=bounds)


def read_pathset(path):
    r = Reader(path)
    if r.take(4) != b'PTH1': raise FormatError(f'{path}: expected PTH1')
    count, current = r.u32(), r.u32()
    paths = []
    for _ in range(count):
        name = r.text(32)
        n, unknown = r.u32(), r.u32()
        points = []
        for _ in range(n):
            misc = r.u32()
            points.append(r.vec())
        typ, spacing, padding = r.u8(), r.u8(), r.u16()
        if typ == 1 and len(points) % 2: raise FormatError(f'{path}: odd directed-point count')
        paths.append(dict(name=name, points=points, type=typ, spacing=spacing))
    if r.offset != len(r.data): raise FormatError(f'{path}: unexpected trailing bytes')
    return paths


def read_inst(path):
    r, result = Reader(path), []
    while r.offset < len(r.data):
        room, modifiers, typ = r.u16(), r.u16(), r.u8()
        name = r.text(typ & 127)
        if typ & 128:
            dx, dz = r.f32(), r.f32()
            axes = [[dx, 0, dz], [0, 1, 0], [-dz, 0, dx]]
        else:
            axes = r.vecs(3)
        result.append(dict(room=room, modifiers=modifiers, name=name, axes=axes, position=r.vec()))
    return result


def read_bai(path):
    r = Reader(path)
    if r.take(4) != b'CAI1': raise FormatError(f'{path}: expected CAI1')
    ni, nr = r.u16(), r.u16()
    roads = []
    def end():
        return dict(intersection=r.u32(), unknown=r.u16(), rule=r.u32(), index=r.u32(), origin=r.vec(), axis=r.vec())
    for _ in range(nr):
        rd = dict(id=r.u16(), n=r.u16(), flags=r.u16())
        n = rd['n']
        if n < 2: raise FormatError(f'{path}: road {rd["id"]} has fewer than two sections')
        rd.update(rooms=r.values('H', r.u16()), halfWidth=r.f32(), speed=r.f32())
        for side in ('right', 'left'):
            s = dict(lanes=r.u16(), trams=r.u16(), trains=r.u16(), sidewalks=r.u16(), ambient=r.u16())
            s['laneDistances'] = r.values('f', s['lanes'] * n)
            s['distances'], s['unknown'] = r.values('f', n), r.values('f', 11+s['lanes'])
            s['laneVertices'] = [r.vecs(n) for _ in range(s['lanes'])]
            s['sidewalkCenter'] = r.vecs(n)
            s['tramVertices'], s['trainVertices'] = [r.vecs(n) for _ in range(s['trams'])], [r.vecs(n) for _ in range(s['trains'])]
            s['inner'], s['outer'] = r.vecs(n), r.vecs(n)
            rd[side] = s
        rd['distances'] = r.values('f', n)
        for key in ('center', 'x', 'y', 'z', 'tangents'): rd[key] = r.vecs(n)
        rd['end'], rd['start'] = end(), end()
        roads.append(rd)
    intersections = []
    for _ in range(ni):
        it = dict(id=r.u16(), room=r.u16(), center=r.vec())
        it['roads'] = r.values('I', r.u16())
        intersections.append(it)
    # Consume and validate culling when present; the exporter recalculates it.
    if r.offset < len(r.data):
        count = r.u32()
        for _ in range(2 * count): r.values('H', r.u16())
    return dict(roads=roads, intersections=intersections)
