"""Split the raw INST modifiers of the INST meshes into their flags and paint job."""
import copy
import sys
import MigrationHelper


# The bits of the modifiers: the low byte is the paint job, the game reads only these bits of the high byte
FLAGS = {'instLandmark': 0x0100, 'instBanger': 0x0200, 'instSimpleCollision': 0x0400, 'instMultiroom': 0x2000}
PAINT_JOB_MASK = 0x00ff
DEFAULT_MODIFIERS = 0x0100  # what the exporter wrote when the value was missing


def decode(modifiers):
    values = {name: bool(modifiers & bit) for name, bit in FLAGS.items()}
    values['instPaintJob'] = modifiers & PAINT_JOB_MASK
    return values


def migrate_city(source):
    data = copy.deepcopy(source)
    ignored = 0
    for mesh in data.get('meshes') or []:
        settings = mesh.get('settings')
        if not settings or settings.get('type') != 'instMesh':
            continue
        modifiers = int(settings.pop('instModifiers', DEFAULT_MODIFIERS)) & 0xffff
        settings.update(decode(modifiers))
        if modifiers & ~(PAINT_JOB_MASK | sum(FLAGS.values())):
            ignored += 1
    if ignored > 0:
        print(str(ignored) + ' INST meshes had modifiers bits that the game does not read: they were removed')
    return data


def process_folder(helper):
    if helper.get_pref('coreVersion', 0) >= 7:
        return
    city = migrate_city(helper.read_local('city.json.gz', True))
    helper.read_and_backup('city.json.gz', True)
    preferences = helper.read_and_backup('preferences.json', False)
    helper.save(city, 'city.json.gz', True)
    preferences['coreVersion'] = 7
    helper.save(preferences, 'preferences.json', False)


if __name__ == '__main__' or 'mh' in globals():
    process_folder(MigrationHelper.MigrationHelper(sys.argv[1]))
    print('done 7')
