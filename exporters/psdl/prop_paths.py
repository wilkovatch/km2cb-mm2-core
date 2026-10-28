"""Standalone prop rules: compact native strips when their evaluated output agrees."""
import math
import numpy as np
from utils import state_val
from psdl_parts import ExportedCityElement


def point(p):
    return np.asarray(p['position'], dtype=float)


def strip_placements(points, raw_spacing):
    spacing = raw_spacing / 4 if raw_spacing else 5.0
    result = []
    for a, b in zip(points, points[1:]):
        delta = np.subtract(b, a)
        length = float(np.linalg.norm(delta))
        if length < 1e-6:
            continue
        yaw = math.atan2(float(delta[2]), float(-delta[0]))
        for i in range(max(1, int(length / spacing))):
            result.append((np.add(a, delta * (i * spacing / length)), yaw))
    return result


def native_strip(element, ribbon, evaluated, mesh_dict):
    state = element['data']['fields']['state']
    rule = state_val(state, 'propRule', {})
    container = state_val(rule, ribbon, {})
    entries = state_val(container, 'elements', [])
    if not entries and state_val(container, 'element'):
        entries = [state_val(container, 'element')]
    if len(entries) != 1:
        return None
    entry = entries[0]
    typ = state_val(entry, 'type')
    if typ not in ('pathsetStrip', 'line'):
        return None
    if typ == 'line' and (float(state_val(entry, 'start', 0)) != 0 or float(state_val(entry, 'end', 0)) != 0
                          or int(state_val(entry, 'maxNumber', 0)) > 0):
        return None
    models = state_val(entry, 'meshes', [])
    model = state_val(entry, 'mesh') or (models[0] if len(models) == 1 else None)
    if not model:
        return None
    raw = state_val(entry, 'rawSpacing', None) if typ == 'pathsetStrip' else float(state_val(entry, 'elemDistance', 0)) * 4
    if raw is None or not math.isfinite(float(raw)) or int(raw) != raw or not 0 <= raw <= 255:
        return None
    names = state_val(state, 'ribbonNames', ['main'])
    index = names.index(ribbon)
    segments = element['points']['ribbons'][index]['segments']
    strips, expected = [], []
    for segment in segments:
        vertices = []
        for section in segment['sections']:
            a, b = point(section['start']), point(section['end'])
            vertices.append((a + b) / 2)
        strips.append(vertices)
        expected.extend(strip_placements(vertices, int(raw)))
    if len(expected) != len(evaluated):
        return None
    stem = str(model).replace('\\', '/').split('/')[-1].rsplit('.', 1)[0]
    for (pos, yaw), actual in zip(expected, evaluated):
        actual_stem = mesh_dict[int(actual['meshId'])]['name'].replace('\\', '/').split('/')[-1].rsplit('.', 1)[0]
        if actual_stem.lower() != stem.lower() or np.linalg.norm(pos - actual['position']) > 0.01:
            return None
        if np.max(np.abs(np.asarray(actual['scale']) - 1)) > 1e-6:
            return None
        quaternion = np.asarray(actual['rotation'], dtype=float)
        target = np.array([0, math.sin(yaw / 2), 0, math.cos(yaw / 2)])
        dot = min(1.0, abs(float(np.dot(quaternion, target))))
        if math.degrees(2 * math.acos(dot)) > 0.1:
            return None
    return stem, int(raw), strips


def export_prop_paths(processor, result):
    for element in processor.data.get('propPaths') or []:
        for line in element['data'].get('propLines') or []:
            native = native_strip(element, line['name'], line['props'], processor.data['meshDict'])
            if native is not None:
                model, spacing, strips = native
                for vertices in strips:
                    part = ExportedCityElement()
                    part.name, part.mat = '0_PTH', 'NONE'
                    part.vertices = [v.tolist() for v in vertices]
                    part.properties.update(object=model, flags='2', spacing=str(spacing))
                    result.append(part)
            else:
                # Standalone psdl containers export their evaluated props, unlike native road rules.
                for prop in line['props']:
                    part = ExportedCityElement()
                    part.name, part.mat = '0_PTH', 'NONE'
                    model = processor.data['meshDict'][int(prop['meshId'])]['name']
                    part.properties.update(object=model.replace('\\', '/').split('/')[-1].rsplit('.', 1)[0], flags='1')
                    part.translation, part.rotation, part.scale = prop['position'], prop['rotation'], prop['scale']
                    result.append(part)
