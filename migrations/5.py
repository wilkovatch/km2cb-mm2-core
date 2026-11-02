"""All the format changes since core version 4, before the builder decodes the city:
- the experimental standalone prop rules are removed
- the race opponents move to owned Low Poly splines
- the containers and the elements of the prop rules become props types: a container with a single element (line, parkedCars,
  pathsetStrip) becomes a flat state of its type, the elements in the lists of the other containers are renamed where a container
  had the same name (psdl to psdlProp, custom to customProp), and the propContainer and propElem presets move to a category for
  each type (props/<type>)
"""
import copy
import math
import sys
import uuid
import MigrationHelper

FLAT_TYPES = ('line', 'parkedCars', 'pathsetStrip')
ITEM_TYPES = {'psdl': 'psdlProp', 'custom': 'customProp', 'line': 'line', 'psdlProp': 'psdlProp', 'customProp': 'customProp'}
DEFAULT_PRESET = 'Default'


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


# Props types

def migrate_old_strips(value):
    # the first version of the type had a list of elements, with the spacing as the raw byte of the file
    if isinstance(value, list):
        for item in value:
            migrate_old_strips(item)
    elif isinstance(value, dict):
        if value.get('type') == 'pathsetStrip':
            elements = value.pop('elements', None)
            if elements:
                if len(elements) > 1:
                    print('Keeping only the first of the ' + str(len(elements)) + ' elements of a pathset prop line strip')
                value['element'] = elements[0]
            if 'rawSpacing' in value:
                raw = value.pop('rawSpacing')
                value['elemDistance'] = raw / 4 if raw > 0 else 5
        for item in value.values():
            migrate_old_strips(item)


class Links:
    """The new names of the presets of a type (name collisions in a category get a suffix)."""

    def __init__(self):
        self.names = {}

    def add(self, source, type_name, old, new):
        self.names[(source, type_name, old)] = new

    def get(self, source, type_name, old):
        return self.names.get((source, type_name, old), old)


def link(state, source, type_name, old, links):
    # an empty name is an unlinked state: it stays, as the exporter of the prop rules reads it
    if old is None:
        state.pop('name', None)
    else:
        state['name'] = links.get(source, type_name, old)


def migrate_item(item, links):
    """An element of a list, None if the new type can't be in a list."""
    if 'elements' in item or item.get('type') not in ITEM_TYPES:
        print('Leaving out a props element of type ' + str(item.get('type')) + ': it can\'t be in a list anymore')
        return None
    old_type = item['type']
    res = dict(item)
    res['type'] = ITEM_TYPES[old_type]
    link(res, 'propElem', res['type'], item.get('name'), links)
    return res


def migrate_container(container, links):
    """The state of a props container, or of a preset of one."""
    container_type = container.get('type')
    if 'element' in container or container_type in FLAT_TYPES:
        element = container.get('element') or {}
        res = dict(element)
        for key, value in container.items():
            if key not in ('element', 'name'):
                res[key] = value
        if container.get('name'):
            link(res, 'propContainer', container_type, container['name'], links)
        else:
            link(res, 'propElem', container_type, element.get('name'), links)
        if container_type:
            res['type'] = container_type
        return res
    res = dict(container)
    if 'name' in container:
        link(res, 'propContainer', container_type, container['name'], links)
    if 'elements' in container:
        items = [migrate_item(item, links) for item in container['elements'] or []]
        res['elements'] = [item for item in items if item is not None]
    return res


def migrate_rule(rule, links):
    """The containers are the values of the rule: a road state and a prop rule preset also have a type, of the road."""
    for key, value in rule.items():
        if isinstance(value, dict):
            rule[key] = migrate_container(value, links)


def migrate_rules_in(value, links):
    """Every prop rule, at any depth."""
    if isinstance(value, list):
        for item in value:
            migrate_rules_in(item, links)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == 'propRule' and isinstance(item, dict):
                migrate_rule(item, links)
            else:
                migrate_rules_in(item, links)


def unique_name(name, existing):
    if name not in existing:
        return name
    n = 2
    while name + ' ' + str(n) in existing:
        n += 1
    return name + ' ' + str(n)


def move_presets(presets, links):
    """Moves the presets to their new categories, giving the links first as the states are migrated afterwards."""
    moved = {}
    pending = []
    for source in ('propContainer', 'propElem'):
        for preset in presets.pop(source, None) or []:
            old_type = preset.get('type')
            new_type = ITEM_TYPES.get(old_type) if source == 'propElem' else old_type
            if new_type is None:
                if preset.get('name') != DEFAULT_PRESET:
                    print('Leaving out the preset ' + str(preset.get('name')) + ' of ' + source + ': its type is ' + str(old_type))
                continue
            pending.append((source, new_type, preset))
            category = moved.setdefault(new_type, {})
            new_name = unique_name(preset.get('name', ''), category)
            category[new_name] = None
            links.add(source, new_type, preset.get('name', ''), new_name)
    for source, new_type, preset in pending:
        state = migrate_item(preset, links) if source == 'propElem' else migrate_container(preset, links)
        if state.get('name') not in moved[new_type] or moved[new_type][state.get('name')] is not None:
            state['name'] = links.get(source, new_type, preset.get('name', ''))
        moved[new_type][state['name']] = state
    for new_type, category in moved.items():
        # the first one is the default one
        states = [state for name, state in category.items() if name != DEFAULT_PRESET]
        default = category.get(DEFAULT_PRESET) or dict(name=DEFAULT_PRESET, type=new_type)
        presets['props/' + new_type] = [default] + states


def migrate_presets(source):
    """The new presets and the new names of the moved ones (for the states linked to them)."""
    data = copy.deepcopy(source)
    links = Links()
    presets = data.get('presets')
    if not isinstance(presets, dict):
        return data, links
    remove_prop_path_presets(presets)
    migrate_old_strips(presets)
    move_presets(presets, links)
    for preset in presets.get('roadPropRule') or []:
        migrate_rule(preset, links)
    for category, states in presets.items():
        if not category.startswith('props/') and category != 'roadPropRule':
            migrate_rules_in(states, links)
    return data, links


def migrate_city(source, links=None):
    data = copy.deepcopy(source)
    remove_prop_paths(data)
    migrate_opponents(data)
    migrate_old_strips(data)
    migrate_rules_in(data, links or Links())
    return data


def process_folder(helper):
    if helper.get_pref('coreVersion', 0) >= 5:
        return
    old_presets = helper.read_local('presets.json', False)
    presets, links = migrate_presets(old_presets)
    city = migrate_city(helper.read_local('city.json.gz', True), links)
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
