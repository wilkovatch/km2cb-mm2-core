"""All the format changes since core version 4, before the builder decodes the city:
- the experimental standalone prop rules are removed
"""
import copy
import sys
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


def migrate_presets(source):
    data = copy.deepcopy(source)
    presets = data.get('presets')
    if isinstance(presets, dict):
        remove_prop_path_presets(presets)
    return data


def migrate_city(source):
    data = copy.deepcopy(source)
    remove_prop_paths(data)
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
