"""Race ownership and the adapter from authored opponent splines to the AIMAP/OPP writer."""
import copy
import json
import os
import re
from utils import state_val
from writers.pathset_writer import PATHSETWriter
from writers import report

OWNER = '_propertyContainerId'
IDENTITY = '_elementContainerId'


def races(data):
    properties = data.get('cityProperties') or {}
    for key, prefix in (('blitzRaces', 'blitz'), ('circuitRaces', 'circuit'), ('checkpointRaces', 'race')):
        for index, race in enumerate(state_val(properties, key, []) or []):
            yield prefix + str(index), race


def validate_ownership(data):
    known = {}
    for race_id, race in races(data):
        identity = state_val(race, IDENTITY, '')
        if identity and identity in known:
            report.error('Races have the same container identity: ' + race_id + ' and ' + known[identity])
        if identity:
            known[identity] = race_id
    for element in data.get('customElements') or []:
        state = element['data']['fields']['state']
        owner = state_val(state, OWNER, '')
        if element.get('type') == 'mapLabel':
            if not owner or owner != state_val(data.get('cityProperties'), IDENTITY, ''):
                report.error('Map label has no valid Hudmap container: ' + element['data']['name'], element=element['data']['name'], kind='customElement')
            continue
        if (owner and owner not in known) or (element.get('type') == 'opponent' and not owner):
            report.error('Element has no valid race container: ' + element['data']['name'], element=element['data']['name'], kind='customElement')
    for mesh in data.get('meshInstances') or []:
        owner = state_val(mesh.get('settings'), OWNER, '')
        if owner and owner not in known:
            report.error('Prop has no valid race container: ' + mesh['name'], element=mesh['name'], kind='meshInstance')


def opponents(data, race, professional):
    owner = state_val(race, IDENTITY, '')
    result = []
    if owner:
        for element in data.get('customElements') or []:
            state = element['data']['fields']['state']
            if element.get('type') != 'opponent' or state_val(state, OWNER, '') != owner:
                continue
            if bool(state_val(state, 'difficulty', 0)) != professional:
                continue
            # Copy the state fields rather than mutating the export input shared with other writers.
            adapted = copy.deepcopy(state)
            adapted['waypoints'] = [{'waypoint': {'localPosition': dict(zip(('x', 'y', 'z'), p['position']))}}
                                    for p in (element.get('points') or {}).get('spline') or []]
            result.append(adapted)
    # Also accept old export-JSON inputs used by external scripts and saved fixtures.
    legacy = state_val(race, 'opponents_professional' if professional else 'opponents', {}) or {}
    result.extend(state_val(legacy, 'opponents', []) or [])
    if professional and not result:
        return opponents(data, race, False)
    return result


def write_props(scene, data, layout):
    folder = layout.dir('race')
    manifest = os.path.join(folder, '.km2-race-props.json')
    previous = []
    if os.path.exists(manifest):
        with open(manifest, encoding='utf-8') as stream:
            previous = json.load(stream)
    names = []
    present = {part.properties.get('race') for part in scene.parts}
    for race_id, race in races(data):
        owner = state_val(race, IDENTITY, '')
        if not owner or owner not in present:
            continue
        name = race_id + '.pathset'
        PATHSETWriter(scene, layout.psdl).write(os.path.join(folder, name), owner)
        names.append(name)
    for name in previous:
        if isinstance(name, str) and re.fullmatch(r'(blitz|circuit|race)\d+\.pathset', name) and name not in names:
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                os.remove(path)
    temporary = manifest + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump(names, stream)
    os.replace(temporary, manifest)


# Colours of the legs of the routes drawn over the city by the program (see check_opponents)
LEG_COLOURS = {'road': '#2e9e44', 'straight': '#e08a00', 'blocked': '#d62828'}


def opponent_elements(data, targets=None):
    # the opponent custom elements with their race (race id, race state), only the targets if given: a list of
    # {"kind": "customElement", "id": <index in the export JSON>} and {"kind": "propertyContainer", "id": <race identity>}
    by_owner = {}
    for race_id, race in races(data):
        identity = state_val(race, IDENTITY, '')
        if identity:
            by_owner[identity] = (race_id, race)
    elements = set()
    owners = set()
    for target in targets or []:
        if target.get('kind') == 'customElement':
            elements.add(target.get('id'))
        elif target.get('kind') == 'propertyContainer':
            owners.add(target.get('id'))
    res = []
    for index, element in enumerate(data.get('customElements') or []):
        if element.get('type') != 'opponent':
            continue
        owner = state_val(element['data']['fields']['state'], OWNER, '')
        if owner not in by_owner:
            continue
        if targets is not None and element.get('id', index) not in elements and owner not in owners:
            continue
        res.append((element, by_owner[owner]))
    return res


def check_opponents(data, jp, parts, targets=None, summary=False, errors=True):
    # reports the opponents that don't reach the finish as the game drives them (traffic/opponents.py): jp is the
    # JsonProcessor that made the parts (with its network); summary: also an info item per opponent with its route;
    # errors: the problems are errors (otherwise warnings, as in an export, which they don't stop)
    from traffic.opponents import OpponentMap
    found = opponent_elements(data, targets)
    if not found:
        if summary:
            report.info('No opponents to check')
        return
    if jp.network is None:
        report.error('The opponents were not checked: the traffic was not exported')
        return
    city = OpponentMap.from_processor(jp, parts)

    def overlay(legs):
        return [{'type': 'polyline', 'points': [[float(c) for c in p] for p in leg.points],
                 'color': LEG_COLOURS.get(leg.kind, '#d62828')} for leg in legs]

    for element, (race_id, race) in found:
        name = element['data']['name']
        state = element['data']['fields']['state']
        model = state_val(state, 'carModel', None)
        if model is None:
            report.error('The opponent has no car', element=name, kind='customElement', code='opponent_no_car')
            continue
        pos = state_val(model, 'localPosition', {'x': 0, 'y': 0, 'z': 0})
        start = (pos['x'], pos['y'], pos['z'])
        waypoints = [p['position'] for p in (element.get('points') or {}).get('spline') or []]
        route = city.check(start, waypoints, circuit=race_id.startswith('circuit'))
        for issue in route.issues:
            kwargs = dict(element=name, kind='customElement', code=issue.code,
                          position=[float(c) for c in issue.position])
            if issue.leg is not None:
                kwargs['overlay'] = overlay([issue.leg])
            (report.error if issue.level == 'error' and errors else report.warning)(issue.message, **kwargs)
        if summary:
            errors = sum(1 for i in route.issues if i.level == 'error')
            text = ('reaches the finish' if errors == 0 else 'gets stuck or goes astray (' + str(errors) + (' errors)' if errors > 1 else ' error)'))
            straight = sum(1 for leg in route.legs if leg.kind != 'road')
            if straight > 0:
                text += ', ' + str(straight) + (' legs' if straight > 1 else ' leg') + ' off the roads'
            report.info(text, element=name, kind='customElement', code='opponent_route',
                        position=[float(c) for c in start], overlay=overlay(route.legs))
