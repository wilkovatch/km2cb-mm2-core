"""Core prop placers: native line paths, or the exact individually evaluated props."""
import math
from psdl_parts import ExportedCityElement
from utils import state_val


def model_name(model):
    return str(model).replace('\\', '/').split('/')[-1].rsplit('.', 1)[0]


def export_prop_placer(processor, element, result):
    if element.get('validationError'):
        raise ValueError(element['validationError'])
    state = element['data']['fields']['state']
    if element['type'] == 'propLine':
        container = state_val(state_val(state, 'propRule', {}), 'main', {})
        entry = state_val(container, 'element', {})
        model = state_val(entry, 'mesh', '')
        if not model:
            return
        distance = state_val(entry, 'elemDistance', 5)
        if not isinstance(distance, (int, float)) or not math.isfinite(distance) or not 0.25 <= distance <= 63.75 or distance * 4 != int(distance * 4):
            raise ValueError('Prop line spacing must be 0.25 to 63.75 metres in quarter-metre steps')
        spacing = int(distance * 4)
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
        for prop in line['props']:
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
