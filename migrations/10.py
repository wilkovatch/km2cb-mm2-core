"""The front-only building lines (removed from the builder) become polygonal buildings.

A front-only line was a row of facades along its points with a roof over the whole outline. A polygonal building is the
closed outline through the same points, in the same order (the builder turns its walls so that they face outwards): its
height and roof texture are the ones of the line, and its walls get the fronts of the buildings of the line. When all
the fronts are the same, they become the side shared by every wall, otherwise each wall gets the front of the building
of its segment (the one from the last point to the first gets the front of the building closing the loop, or of the
last building for a line that wasn't a loop). A front-only line with less than three points stays a building line.
The saved references to the building lines (their indices) follow them. The other lines lose frontOnly, height and
roofTex. The front-only line presets become polygonal building presets, and a default polygonal building preset is
added if missing.
"""
import copy
import os
import sys
import MigrationHelper

LINE_KEYS = ('frontOnly', 'height', 'roofTex')
# the parameters of the lines kept by the polygonal buildings (also when they are not in the state)
SHARED_KEYS = ('fixBound', 'hudmapCategory', 'uMult', 'vMult')


def strip_line_state(state):
    if isinstance(state, dict):
        for key in LINE_KEYS:
            state.pop(key, None)


def polygon_state(line_state, side_state, individual, name):
    res = dict(type=line_state.get('type', 'psdl'), height=line_state.get('height', 10.0), roofTex=line_state.get('roofTex', ''),
               individualSides=individual, sideState=copy.deepcopy(side_state))
    for key in SHARED_KEYS:
        if key in line_state:
            res[key] = copy.deepcopy(line_state[key])
    res['name'] = name
    return res


def default_side(presets):
    sides = (presets or {}).get('buildingSide') or []
    side = copy.deepcopy(sides[0]) if sides else dict(type='psdl')
    side['name'] = ''
    side.pop('Name', None)
    return side


def segment_buildings(line, dividing):
    # the index of the building of the segment starting at each point (the last one is the segment closing the outline)
    ids = line.get('linePoints') or []
    res = []
    current = -1
    for i, point in enumerate(ids):
        if i == 0 or (i < len(ids) - 1 and dividing.get(point, False)):
            current += 1
        res.append(current + 1 if i == len(ids) - 1 else current)
    return res


def convert_line(line, dividing, moved_presets, fallback_side):
    """The polygonal building made from a front-only line (without its id), or None if it has less than three points."""
    state = line.get('state') or {}
    ids = line.get('linePoints') or []
    first_index = {}
    for i, point in enumerate(ids):
        first_index.setdefault(point, i)
    kept = [i for i, point in enumerate(ids) if first_index[point] == i]
    if len(kept) < 3:
        return None
    buildings = line.get('buildings') or []
    fronts = []
    segments = segment_buildings(line, dividing)
    for i in kept:
        building = buildings[min(segments[i], len(buildings) - 1)] if buildings else None
        fronts.append((building or {}).get('frontState'))
    known = [front for front in fronts if front is not None]
    shared = known[0] if known else fallback_side
    individual = any(front != shared for front in known)
    name = state.get('name', '') if state.get('name', '') in moved_presets else ''
    res = dict(name=line.get('name'), state=polygon_state(state, shared, individual, name),
               instanceState=copy.deepcopy(line.get('instanceState') or {}), points=[ids[i] for i in kept])
    if individual:
        res['wallStates'] = [copy.deepcopy(front) for front in fronts]
    return res


def remap_references(value, line_map):
    # the references to the building lines ({kind, id}, the id being the index of the line) follow them
    if isinstance(value, dict):
        if value.get('kind') == 'buildingLine' and isinstance(value.get('id'), int) and value['id'] in line_map:
            value['kind'], value['id'] = line_map[value['id']]
            return
        for item in value.values():
            remap_references(item, line_map)
    elif isinstance(value, list):
        for item in value:
            remap_references(item, line_map)


def migrate_city(source, moved_presets=frozenset(), presets=None):
    data = copy.deepcopy(source)
    dividing = {p['id']: bool(p.get('dividing')) for p in data.get('terrainPoints') or []}
    polygons = data.get('polygonalBuildings') or []
    fallback_side = default_side(presets)
    kept_lines = []
    line_map = {}
    converted = []
    short = []
    for index, line in enumerate(data.get('buildingLines') or []):
        state = line.get('state') or {}
        polygon = convert_line(line, dividing, moved_presets, fallback_side) if state.get('frontOnly') else None
        if polygon is None:
            if state.get('frontOnly'):
                short.append(line.get('name') or 'Building ' + str(index + 1))
            strip_line_state(state)
            line_map[index] = ('buildingLine', len(kept_lines))
            line['id'] = len(kept_lines)
            kept_lines.append(line)
        else:
            line_map[index] = ('polygonalBuilding', len(polygons))
            polygon = dict(id=len(polygons), **polygon)
            polygons.append(polygon)
            converted.append(polygon['name'] or 'Building ' + str(index + 1))
    data['buildingLines'] = kept_lines
    if polygons:
        data['polygonalBuildings'] = polygons
    for key in ('customElements', 'lowLevelElements'):
        for element in data.get(key) or []:
            remap_references(element.get('state'), line_map)
            remap_references(element.get('source'), line_map)
    return data, converted, short


def default_roof(presets):
    # the roof texture of the default building preset
    buildings = (presets or {}).get('building') or []
    return buildings[0].get('topTexture', '') if buildings else ''


def preset_polygon(line_preset, side, roof=''):
    name = line_preset.get('name') or line_preset.get('Name') or 'Default'
    res = polygon_state(line_preset, side, False, name)
    if not res['roofTex']:
        res['roofTex'] = roof
    res['Name'] = name
    return res


def migrate_presets(source):
    """The presets, and the names of the line presets that became polygonal building presets."""
    data = copy.deepcopy(source)
    presets = data.get('presets') if isinstance(data, dict) else None
    if not isinstance(presets, dict):
        return data, set()
    lines = presets.get('buildingLine') or []
    side = default_side(presets)
    polygons = presets.get('polygonalBuilding')
    if polygons is None and lines:
        polygons = presets['polygonalBuilding'] = [preset_polygon(dict(lines[0], name='Default'), side, default_roof(presets))]
    moved = set()
    kept = []
    for index, preset in enumerate(lines):
        if index > 0 and preset.get('frontOnly'):
            polygon = preset_polygon(preset, side, default_roof(presets))
            if polygons is not None and not any(p.get('name') == polygon['name'] for p in polygons):
                polygons.append(polygon)
            moved.add(polygon['name'])
            continue
        strip_line_state(preset)
        kept.append(preset)
    if lines:
        presets['buildingLine'] = kept
    return data, moved


def process_folder(helper):
    if helper.get_pref('coreVersion', 0) >= 10:
        return
    old_presets = helper.read_local('presets.json', False) if os.path.isfile(helper.path + 'presets.json') else None
    presets, moved = migrate_presets(old_presets) if old_presets is not None else (None, set())
    city, converted, short = migrate_city(helper.read_local('city.json.gz', True), moved, (presets or {}).get('presets'))
    # Validate the complete conversion before backing up or writing any file. Publish the version last.
    helper.read_and_backup('city.json.gz', True)
    preferences = helper.read_and_backup('preferences.json', False)
    if presets is not None and presets != old_presets:
        helper.read_and_backup('presets.json', False)
        helper.save(presets, 'presets.json', False)
    helper.save(city, 'city.json.gz', True)
    if converted:
        print('front-only building lines that became polygonal buildings: ' + ', '.join(converted))
    if short:
        print('front-only building lines with less than three points, now normal building lines: ' + ', '.join(short))
    preferences['coreVersion'] = 10
    helper.save(preferences, 'preferences.json', False)


if __name__ == '__main__' or 'mh' in globals():
    process_folder(MigrationHelper.MigrationHelper(sys.argv[1]))
    print('done 10')
