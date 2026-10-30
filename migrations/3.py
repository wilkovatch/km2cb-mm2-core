"""Move manual city-property decals to spline low-level elements. Automatic rail settings are removed, not baked."""
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
    for i, decal in enumerate(properties.get('decals') or []):
        ids = []
        for entry in decal.get('points') or []:
            value = (entry.get('point') or {}).get('localPosition')
            if value is None:
                continue  # legacy export also omitted entries without a point
            position = {k: float(value.get(k, 0)) for k in ('x', 'y', 'z')} if isinstance(value, dict) else dict(zip(('x', 'y', 'z'), value))
            if len(position) != 3 or not all(math.isfinite(v) for v in position.values()):
                raise ValueError('invalid position in decal ' + str(i + 1))
            points.append(dict(id=point_id, position=position, dividing=False, linkType=0,
                               elementType=0, elementId=-1, anchorIndex=-1, percent=0))
            ids.append(point_id)
            point_id += 1
        width = float(decal.get('width') or 0)
        if not math.isfinite(width):
            raise ValueError('invalid width in decal ' + str(i + 1))
        elements.append(dict(id=element_id, name=decal.get('name') or 'Decal ' + str(i + 1),
                             state=dict(type='decal', texture=decal.get('texture') or '', width=width,
                                        curveType=2, segments=20, hermiteTension=0.5),
                             points=dict(spline=ids), containerId=-1))
        element_id += 1
    for key in ('decals', 'cableCarRailDecals', 'cableCarRailTexture', 'cableCarRailWidth'):
        properties.pop(key, None)
    data['cityProperties'] = properties
    return data


def process_folder(helper):
    if helper.get_pref('coreVersion', 0) >= 3:
        return
    city = migrate_city(helper.read_local('city.json.gz', True))
    # Validate the complete conversion before backing up or writing either file. Publish the version last.
    helper.read_and_backup('city.json.gz', True)
    preferences = helper.read_and_backup('preferences.json', False)
    helper.save(city, 'city.json.gz', True)
    preferences['coreVersion'] = 3
    helper.save(preferences, 'preferences.json', False)


if __name__ == '__main__' or 'mh' in globals():
    process_folder(MigrationHelper.MigrationHelper(sys.argv[1]))
    print('done 3')
