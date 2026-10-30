"""Move city-property train lines to native MM2 train spline elements, preserving authored controls, and give the mesh
instances their type (individualProp or instMesh) from their former prop flag."""
import copy
import math
import sys
import MigrationHelper


def migrate_city(data):
    data = copy.deepcopy(data)
    properties = data.get('cityProperties') or {}
    points = data['terrainPoints'] = data.get('terrainPoints') or []
    elements = data['lowLevelElements'] = data.get('lowLevelElements') or []
    point_id = max((p['id'] for p in points), default=-1) + 1
    element_id = max((e['id'] for e in elements), default=-1) + 1
    for i, line in enumerate(properties.get('trainLines') or []):
        ids = []
        for entry in line.get('points') or []:
            value = (entry.get('point') or {}).get('localPosition')
            if value is None:
                continue
            position = {k: float(value.get(k, 0)) for k in ('x', 'y', 'z')} if isinstance(value, dict) else dict(zip(('x', 'y', 'z'), value))
            if len(position) != 3 or not all(math.isfinite(v) for v in position.values()):
                raise ValueError('invalid position in train line ' + str(i + 1))
            points.append(dict(id=point_id, position=position, dividing=False, linkType=0,
                               elementType=0, elementId=-1, anchorIndex=-1, percent=0))
            ids.append(point_id)
            point_id += 1
        elements.append(dict(id=element_id, name=line.get('name') or 'Train ' + str(i + 1),
                             state=dict(type='train', curveType=3, segments=20),
                             points=dict(spline=ids), containerId=-1))
        element_id += 1
    properties.pop('trainLines', None)
    data['cityProperties'] = properties
    migrate_meshes(data)
    return data


def migrate_meshes(data):
    for mesh in data.get('meshes') or []:
        settings = mesh.get('settings') or {}
        if 'type' not in settings:
            settings['type'] = 'individualProp' if settings.get('prop') else 'instMesh'
        settings.pop('prop', None)
        if settings['type'] == 'individualProp':
            settings.pop('instModifiers', None)  # props are pathset entries, the INST flags don't apply
        mesh['settings'] = settings


def process_folder(helper):
    if helper.get_pref('coreVersion', 0) >= 4:
        return
    city = migrate_city(helper.read_local('city.json.gz', True))
    helper.read_and_backup('city.json.gz', True)
    preferences = helper.read_and_backup('preferences.json', False)
    helper.save(city, 'city.json.gz', True)
    preferences['coreVersion'] = 4
    helper.save(preferences, 'preferences.json', False)


if __name__ == '__main__' or 'mh' in globals():
    process_folder(MigrationHelper.MigrationHelper(sys.argv[1]))
    print('done 4')
