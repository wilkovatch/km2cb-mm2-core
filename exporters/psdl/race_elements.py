"""Race ownership and the adapter from authored opponent splines to the AIMAP/OPP writer."""
import copy
import json
import os
import re
from utils import state_val
from common.pathset_writer import PATHSETWriter
from common import report

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
    present = {scene.get_property_container(obj).get('race') for obj in scene.get_object_list()}
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
