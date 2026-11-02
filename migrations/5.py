"""All the format changes since core version 4, before the builder decodes the city:
- the experimental standalone prop rules are removed
- the race opponents move to owned Low Poly splines
"""
import copy
import math
import sys
import uuid
import MigrationHelper



# Standalone prop rules

def remove_prop_paths(data):
    data.pop('propPaths', None)
    for key in ('customElements', 'lowLevelElements'):
        if key in data:
            data[key] = [e for e in data[key] or [] if (e.get('state') or {}).get('type') != '__propPath']
    # Points can be shared with surviving geometry. Leave their ids and attachments intact.


def remove_prop_path_presets(presets):
    for key in ('customElement/__propPath', 'lowLevel/__propPath'):
        presets.pop(key, None)


# Race opponents

def migrate_opponents(data):
    properties = data.get('cityProperties') or {}
    points = data['terrainPoints'] = data.get('terrainPoints') or []
    key = 'customElements' if 'customElements' in data else 'lowLevelElements'
    elements = data[key] = data.get(key) or []
    all_elements = (data.get('customElements') or []) + (data.get('lowLevelElements') or [])
    point_id = max((p['id'] for p in points), default=-1) + 1
    element_id = max((e['id'] for e in all_elements), default=-1) + 1
    for race_key in ('blitzRaces', 'circuitRaces', 'checkpointRaces'):
        for race in properties.get(race_key) or []:
            owner = race.setdefault('_elementContainerId', uuid.uuid4().hex)
            for difficulty, opponents_key in enumerate(('opponents', 'opponents_professional')):
                container = race.get(opponents_key) or {}
                for index, opponent in enumerate(container.get('opponents') or []):
                    state = copy.deepcopy(opponent)
                    controls = []
                    for entry in state.pop('waypoints', []) or []:
                        waypoint = entry.get('waypoint')
                        if waypoint is None:
                            continue
                        value = waypoint.get('localPosition') or {}
                        pos = {axis: float(value.get(axis, 0)) for axis in ('x', 'y', 'z')} if isinstance(value, dict) else dict(zip(('x', 'y', 'z'), value))
                        if len(pos) != 3 or not all(math.isfinite(v) for v in pos.values()):
                            raise ValueError('Invalid opponent waypoint in race ' + race.get('name', ''))
                        points.append(dict(id=point_id, position=pos, dividing=False, linkType=0, elementType=0, elementId=-1, anchorIndex=-1, percent=0))
                        controls.append(point_id)
                        point_id += 1
                    state.update(type='opponent', curveType=2, segments=20, difficulty=difficulty, _propertyContainerId=owner)
                    elements.append(dict(id=element_id, name=(race.get('name') or 'Race') + ' Opponent ' + str(index + 1) + (' (professional)' if difficulty else ''),
                                         state=state, points=dict(spline=controls), containerId=-1))
                    element_id += 1
                race.pop(opponents_key, None)


def migrate_presets(source):
    data = copy.deepcopy(source)
    presets = data.get('presets')
    if isinstance(presets, dict):
        remove_prop_path_presets(presets)
    return data


def migrate_city(source):
    data = copy.deepcopy(source)
    remove_prop_paths(data)
    migrate_opponents(data)
    return data


def process_folder(helper):
    if helper.get_pref('coreVersion', 0) >= 5:
        return
    old_presets = helper.read_local('presets.json', False)
    presets = migrate_presets(old_presets)
    city = migrate_city(helper.read_local('city.json.gz', True))
    # Validate the complete conversion before backing up or writing any file. Publish the version last.
    helper.read_and_backup('city.json.gz', True)
    preferences = helper.read_and_backup('preferences.json', False)
    if presets != old_presets:
        helper.read_and_backup('presets.json', False)
        helper.save(presets, 'presets.json', False)
    helper.save(city, 'city.json.gz', True)
    preferences['coreVersion'] = 5
    helper.save(preferences, 'preferences.json', False)


if __name__ == '__main__' or 'mh' in globals():
    process_folder(MigrationHelper.MigrationHelper(sys.argv[1]))
    print('done 5')
