"""Core prop placers: native line paths, or the exact individually evaluated props."""
import math
import struct
from common import report
from psdl_parts import ExportedCityElement
from utils import state_val, placed_props, PARKED_CARS_TYPES


NATIVE_LINE_TYPE = 'pathsetStrip'
ROUNDING_ALLOWANCE = 0.001


def model_name(model):
    return str(model).replace('\\', '/').split('/')[-1].rsplit('.', 1)[0]


def single(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def path_on_ground(slots, distance, name):
    # The path of a line with each prop on the ground: a point at each slot, so each span has one prop if it's at least as long
    # as the spacing and shorter than twice it. The slots are that far apart on the plan, but in single precision, as the game
    # reads them, a span can come out a little shorter, and the game would skip its prop.
    points = [[single(c) for c in slots[0]]]
    doubled = False
    for slot in slots[1:]:
        a = points[-1]
        b = [single(c) for c in slot]
        length = math.dist(a, b)
        if 0 < length < distance:
            b = [single(a[i] + (b[i] - a[i]) * (distance + ROUNDING_ALLOWANCE) / length) for i in range(3)]
            length = math.dist(a, b)
        doubled = doubled or length >= 2 * distance
        points.append(b)
    if doubled:
        report.warning('some spans of the prop line ' + name + ' are so steep or long that the game places more props than the editor shows',
                       element=name, kind='customElement')
    return points


def export_prop_placer(processor, element, result):
    if element.get('validationError'):
        raise ValueError(element['validationError'])
    state = element['data']['fields']['state']
    entry = state_val(state_val(state, 'propRule', {}), 'main', {})
    if element['type'] == 'propLine' and state_val(entry, 'type') == NATIVE_LINE_TYPE:
        model = state_val(entry, 'mesh', '')
        if not model:
            return
        distance = state_val(entry, 'elemDistance', 5)
        if not isinstance(distance, (int, float)) or not math.isfinite(distance) or not 0.25 <= distance <= 63.75 or distance * 4 != int(distance * 4):
            raise ValueError('Prop line spacing must be 0.25 to 63.75 metres in quarter-metre steps')
        spacing = int(distance * 4)
        if state_val(state, 'projectToGround', True):
            slots = [prop['position'] for line in element['data'].get('propLines') or [] for prop in line['props']]
            if len(slots) < 2:
                return
            points = path_on_ground(slots, distance, element['data']['name'])
        else:
            points = [section['center'] for section in (element.get('spline') or {}).get('sections') or []]
        if len(points) < 2:
            return
        part = ExportedCityElement()
        part.name, part.mat = '0_PTH', 'NONE'
        part.vertices = points
        part.properties.update(object=model_name(model), flags='2', spacing=str(int(spacing)), original_name=element['data']['name'])
        owner = state_val(state, '_propertyContainerId', '')
        if owner:
            part.properties['race'] = owner
        part.source = ('customElement', element['id'])
        result.append(part)
        return
    for line in element['data'].get('propLines') or []:
        if state_val(state_val(state_val(state, 'propRule', {}), line.get('name'), {}), 'type') in PARKED_CARS_TYPES:
            continue  # exported by parked_car_export.py
        for prop in placed_props(line):
            part = ExportedCityElement()
            part.name, part.mat = '0_PTH', 'NONE'
            model = processor.data['meshDict'][int(prop['meshId'])]['name']
            part.properties.update(object=model_name(model), flags='1', original_name=element['data']['name'])
            owner = state_val(state, '_propertyContainerId', '')
            if owner:
                part.properties['race'] = owner
            part.translation, part.rotation, part.scale = prop['position'], prop['rotation'], prop['scale']
            part.source = ('customElement', element['id'])
            result.append(part)
