"""Independent point elements own transform values instead of shared terrain-point references."""
import copy
import math
import sys
import MigrationHelper


POINT_TYPES = {'parkedCar': (True, False), 'decalSingle': (True, True), 'mapLabel': (False, False)}


def vector(value, label):
    if not isinstance(value, dict) or any(isinstance(value.get(axis), bool) or not isinstance(value.get(axis), (int, float))
                                          or not math.isfinite(value[axis]) for axis in ('x', 'y', 'z')):
        raise ValueError('Invalid ' + label + ' in independent point migration')
    return {axis: value[axis] for axis in ('x', 'y', 'z')}


def migrate_city(source):
    data = copy.deepcopy(source)
    points = {p['id']: p for p in data.get('terrainPoints') or []}
    for key in ('customElements', 'lowLevelElements'):
        for element in data.get(key) or []:
            kind = (element.get('state') or {}).get('type')
            if kind not in POINT_TYPES:
                continue
            center = (element.get('points') or {}).get('center')
            if isinstance(center, int) and not isinstance(center, bool):
                if center not in points:
                    raise ValueError('Missing terrain point ' + str(center) + ' for ' + kind)
                center = points[center]
            if not isinstance(center, dict):
                raise ValueError('Missing center for ' + kind)
            value = {'position': vector(center.get('position'), kind + ' position')}
            rotatable, scalable = POINT_TYPES[kind]
            if rotatable and center.get('rotation') is not None:
                value['rotation'] = vector(center['rotation'], kind + ' rotation')
            if scalable and center.get('scale') is not None:
                value['scale'] = vector(center['scale'], kind + ' scale')
            element['points']['center'] = value
    #Other elements and attachments can still reference these ids. The next ordinary save drops unused points.
    return data


def process_folder(helper):
    if helper.get_pref('coreVersion', 0) >= 6:
        return
    city = migrate_city(helper.read_local('city.json.gz', True))
    helper.read_and_backup('city.json.gz', True)
    preferences = helper.read_and_backup('preferences.json', False)
    helper.save(city, 'city.json.gz', True)
    preferences['coreVersion'] = 6
    helper.save(preferences, 'preferences.json', False)


if __name__ == '__main__' or 'mh' in globals():
    process_folder(MigrationHelper.MigrationHelper(sys.argv[1]))
    print('done 6')
