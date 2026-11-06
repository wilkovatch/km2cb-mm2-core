# The decals (custom elements decal and decalSingle) as the DECAL parts written to decals.pathset (see
# writers/decal_writer.py): pairs of points across the strip, as the editor evaluates them.

import math
import os

from psdl_parts import ExportedCityElement
from utils import state_val
from writers import report

# the longest texture name the game reads
DECAL_MAX_TEXTURE_NAME = 31
# the game draws a decal with the room of the middle of its points 0 and 2, so a longer single decal is partly hidden
DECAL_SINGLE_MAX_LENGTH = 25.0


def euler_rotate(p, euler):
    # a vector rotated by euler angles in degrees, as the editor applies them to its points: Z, then X, then Y (the
    # same as lua/decals.lua)
    x, y, z = p
    c, s = math.cos(math.radians(euler[2])), math.sin(math.radians(euler[2]))
    x, y = c * x - s * y, s * x + c * y
    c, s = math.cos(math.radians(euler[0])), math.sin(math.radians(euler[0]))
    y, z = c * y - s * z, s * y + c * z
    c, s = math.cos(math.radians(euler[1])), math.sin(math.radians(euler[1]))
    x, z = c * x + s * z, -s * x + c * z
    return (x, y, z)


def decal_single_corners(point):
    # the corners of a single decal (decalSingle) as the strip pairs of a spline decal: the start pair, then the end one,
    # each from the side with U 1 to the one with U 0 (not lifted)
    position = point['position']
    rotation = point.get('rotation') or (0, 0, 0)
    scale = point.get('scale') or (1, 1, 1)
    corners = []
    for sx, sz in ((-0.5, -0.5), (0.5, -0.5), (-0.5, 0.5), (0.5, 0.5)):
        offset = euler_rotate((sx * scale[0], 0.0, sz * scale[2]), rotation)
        corners.append(tuple(position[i] + offset[i] for i in range(3)))
    return corners


def texture_name(jp, tex):
    # the name of a texture as decals name it (the name of the file, without the extension)
    if tex is None or tex == '':
        return None
    return os.path.splitext(jp.get_tex(tex))[0].lower()


def strip_part(name, texture, vertices):
    elem = ExportedCityElement()
    elem.name = '0_DECAL'
    elem.vertices = vertices
    elem.properties.update(original_name=name, texture=texture, strip_pairs='1')
    elem.mat = 'NONE'
    return elem


def export_decals(jp, res):
    # the parts of the decals of the city (jp: the JsonProcessor, for the textures and the rooms); the edges of the
    # strips are evaluated by the core's JSON components in the editor, not resampled here
    for decal in jp.data.get('customElements') or []:
        if decal.get('type') == 'decalSingle':
            export_single_decal(jp, decal, res)
            continue
        if decal.get('type') != 'decal':
            continue
        state = decal.get('data', {}).get('fields', {}).get('state', {})
        name = decal.get('data', {}).get('name', 'decal')
        texture = texture_name(jp, state_val(state, 'texture', ''))
        pieces = (decal.get('spline') or {}).get('pieces', [])
        if not pieces:
            report.warning('the decal ' + name + ' has less than two distinct usable points, it is not exported')
            continue
        if not texture or len(texture) > DECAL_MAX_TEXTURE_NAME:
            report.warning('the decal ' + name + ' has a missing or overlong texture name, it is not exported')
            continue
        if any(jp.find_block(tuple(section['center'])) < 0 for piece in pieces for section in piece):
            report.warning('the decal ' + name + ' has points outside of the blocks; each piece is visible only with its starting room')
        for piece in pieces:
            if len(piece) != 2 or any(len(section['vertices']) != 2 for section in piece):
                report.warning('the decal ' + name + ' has an invalid strip cross-section, it is not exported')
                continue
            res.append(strip_part(name, texture, [tuple(v) for section in piece for v in section['vertices']]))


def export_single_decal(jp, decal, res):
    # a quad: one piece of two pairs, as the strips of the spline decals
    state = decal.get('data', {}).get('fields', {}).get('state', {})
    name = decal.get('data', {}).get('name', 'decal')
    texture = texture_name(jp, state_val(state, 'texture', ''))
    point = (decal.get('points') or {}).get('center')
    if not point:
        report.warning('the decal ' + name + ' has no point, it is not exported')
        return
    if not texture or len(texture) > DECAL_MAX_TEXTURE_NAME:
        report.warning('the decal ' + name + ' has a missing or overlong texture name, it is not exported')
        return
    scale = point.get('scale') or (1, 1, 1)
    if abs(scale[0]) < 1e-4 or abs(scale[2]) < 1e-4:
        report.warning('the decal ' + name + ' has no width or length, it is not exported')
        return
    if scale[0] * scale[2] < 0:
        report.warning('the decal ' + name + ' is mirrored (a negative width or length), the game draws its back, which is culled')
    if abs(scale[2]) > DECAL_SINGLE_MAX_LENGTH:
        report.warning('the decal ' + name + ' is longer than ' + str(DECAL_SINGLE_MAX_LENGTH) + ' m; it is visible only with its starting room')
    if jp.find_block(tuple(point['position'])) < 0:
        report.warning('the decal ' + name + ' is outside of the blocks; it is visible only with its starting room')
    res.append(strip_part(name, texture, decal_single_corners(point)))
