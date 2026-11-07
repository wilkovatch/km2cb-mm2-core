"""The border meshes of the terrain patches (their rails, removed from the builder) become rail custom elements.

A rail is a spline through the same perimeter points, in the order the builder generated the border mesh (clockwise
seen from above, so that it stays on the same side), with the parameters of the border mesh. It stays open as the
border mesh was (a border mesh through all the points of the perimeter had no edge from the last one to the first).
Its room (the "room" reference, which its points must be on) is the terrain patch.
The presets of the border meshes move to customElement/rail.
"""
import copy
import os
import sys
import MigrationHelper


def clockwise(positions):
    # GeometryHelper.IsPolygonClockwise of the builder
    total = 0.0
    for i, p1 in enumerate(positions):
        p2 = positions[(i + 1) % len(positions)]
        total += (p2['x'] - p1['x']) * (p2['z'] + p1['z'])
    return total > 0


def rail_state(state, instance_state):
    res = {}
    for source in (state, instance_state):
        if isinstance(source, dict):
            res.update(copy.deepcopy(source))
    res.pop('name', None)
    res['type'] = 'rail'
    return res


def migrate_city(source):
    data = copy.deepcopy(source)
    patches = data.get('terrainPatches') or []
    positions = {p['id']: p.get('position') for p in data.get('terrainPoints') or []}
    key = 'lowLevelElements' if 'lowLevelElements' in data and 'customElements' not in data else 'customElements'
    elements = data[key] = data.get(key) or []
    all_elements = (data.get('customElements') or []) + (data.get('lowLevelElements') or [])
    element_id = max((e['id'] for e in all_elements), default=-1) + 1
    count = 0
    for patch_index, patch in enumerate(patches):
        border_meshes = patch.pop('borderMeshes', None) or []
        perimeter = [positions.get(i) for i in patch.get('perimeterPointsIds') or []]
        reverse = len(perimeter) > 2 and all(perimeter) and not clockwise(perimeter)
        for index, border_mesh in enumerate(border_meshes):
            controls = [i for i in border_mesh.get('segmentPointsIds') or [] if i in positions]
            if len(controls) < 2:
                continue
            if reverse:
                controls.reverse()
            state = rail_state(border_mesh.get('state'), border_mesh.get('instanceState'))
            state['curveType'] = 2
            state['room'] = dict(kind='terrainPatch', id=patch_index)
            name = (patch.get('name') or 'Terrain') + ' rail' + (' ' + str(index + 1) if len(border_meshes) > 1 else '')
            elements.append(dict(id=element_id, name=name, state=state, points=dict(spline=controls), containerId=-1))
            element_id += 1
            count += 1
    return data, count


def migrate_presets(source):
    data = copy.deepcopy(source)
    presets = data.get('presets') if isinstance(data, dict) else None
    if not isinstance(presets, dict) or 'terrainPatchBorderMesh' not in presets:
        return data
    rails = presets.setdefault('customElement/rail', [])
    names = {state.get('name') for state in rails}
    for state in presets.pop('terrainPatchBorderMesh') or []:
        name = state.get('name') or 'Default'
        if name not in names:
            rails.append(dict(name=name, **rail_state(state, None)))
            names.add(name)
    return data


def process_folder(helper):
    if helper.get_pref('coreVersion', 0) >= 9:
        return
    old_presets = helper.read_local('presets.json', False) if os.path.isfile(helper.path + 'presets.json') else None
    presets = migrate_presets(old_presets) if old_presets is not None else None
    city, count = migrate_city(helper.read_local('city.json.gz', True))
    # Validate the complete conversion before backing up or writing any file. Publish the version last.
    helper.read_and_backup('city.json.gz', True)
    preferences = helper.read_and_backup('preferences.json', False)
    if presets is not None and presets != old_presets:
        helper.read_and_backup('presets.json', False)
        helper.save(presets, 'presets.json', False)
    helper.save(city, 'city.json.gz', True)
    if count > 0:
        print(str(count) + ' border meshes of the terrain patches became rail elements')
    preferences['coreVersion'] = 9
    helper.save(preferences, 'preferences.json', False)


if __name__ == '__main__' or 'mh' in globals():
    process_folder(MigrationHelper.MigrationHelper(sys.argv[1]))
    print('done 9')
