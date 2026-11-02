"""The rows of the parkedCars props type: the parked cars of the game (race/<city>/<city>_parkedcar[_<race>].pathset).

The game chooses the cars itself: for each slot of a path it places one of the giz_pcar models or nothing, along the
direction of the path, so the models of the editor are only an example and the rows have all the placements of the type.
Its spacing restarts on each span of a path, so a row has a vertex at each slot and a spacing that gives each span
exactly one slot. A race file replaces the main file in that race, so it also has the rows of the whole city.
"""
import json
import math
import os
import re
from pathlib import Path

from common import report
from common.pathset_writer import MAX_PATHS
from race_elements import races, IDENTITY, OWNER
from route_pathset import write_routes
from utils import state_val, state_bool, PARKED_CARS_TYPE

MIN_SPACING = 5  # the game uses 5 m for anything lower
MAX_SPACING_RAW = 255
SPAN_MARGIN = 0.99
SINGLE_SLOT_SPAN = 6
# the game rolls the cars of a sloped span sideways
MAX_SLOPE = 5
MANIFEST = '.km2-parked-car-races.json'


def rotated_forward(rotation):
    # the model Z axis of a placement, from its rotation quaternion
    x, y, z, w = rotation
    return (2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y))


def container_rows(name, state, prop_lines, kind, owner=''):
    rows = []
    rule = state_val(state, 'propRule')
    if not isinstance(rule, dict):
        return rows
    for key, container in rule.items():
        if not isinstance(container, dict) or container.get('type') != PARKED_CARS_TYPE:
            continue
        line = next((l for l in prop_lines or [] if l.get('name') == key), None)
        if line is None or not line.get('props'):
            report.warning('the parked cars ' + key + ' of ' + name + ' have no slots, they are not exported', element=name, kind=kind)
            continue
        rows.append(dict(name=name, kind=kind, owner=owner, slots=[prop['position'] for prop in line['props']],
                         forwards=[rotated_forward(prop['rotation']) for prop in line['props']]))
    return rows


def get_rows(data):
    rows = []
    for road in data.get('roads') or []:
        fields = road['data']['fields']
        if not state_bool(fields.get('instanceState'), 'doNotExport'):
            rows += container_rows(road['data']['name'], fields['state'], road['data'].get('propLines'), 'road')
    for intersection in data.get('intersections') or []:
        for road in intersection.get('roadsThrough') or []:
            rows += container_rows(intersection['data']['name'], road['data']['fields']['state'], road['data'].get('propLines'), 'intersection')
    for element in data.get('customElements') or []:
        state = element['data']['fields']['state']
        rows += container_rows(element['data']['name'], state, element['data'].get('propLines'), 'customElement', state_val(state, OWNER, ''))
    return rows


def get_path(row):
    # the points in MM2 coordinates and the spacing byte of a row: the model of a car lies along the direction of its span
    slots = [tuple(p) for p in row['slots']]
    forward = row['forwards'][0]
    if len(slots) == 1:
        slots.append(tuple(slots[0][i] + forward[i] * SINGLE_SLOT_SPAN for i in range(3)))
    else:
        if sum((slots[1][i] - slots[0][i]) * forward[i] for i in range(3)) < 0:
            slots.reverse()
        # the closing vertex gives its span to the last slot
        slots.append(tuple(2 * slots[-1][i] - slots[-2][i] for i in range(3)))
    spans = [math.dist(a, b) for a, b in zip(slots, slots[1:])]
    raw = max(MIN_SPACING * 4, min(MAX_SPACING_RAW, int(min(spans) * SPAN_MARGIN * 4)))
    spacing = raw / 4
    if min(spans) < spacing or max(spans) >= 2 * spacing:
        report.warning('some parked cars of ' + row['name'] + ' will be missing or doubled: their slots are too close or too far apart',
                       element=row['name'], kind=row['kind'])
    slope = max(math.degrees(math.asin(min(1, abs(b[1] - a[1]) / span))) for a, b, span in zip(slots, slots[1:], spans) if span > 0)
    if slope > MAX_SLOPE:
        report.warning('the game rolls parked cars sideways on a slope: ' + row['name'] + ' reaches ' + str(round(slope, 1)) + ' degrees',
                       element=row['name'], kind=row['kind'])
    return [(-p[0], p[1], p[2]) for p in slots], raw


def write_rows(filepath, rows):
    if len(rows) > MAX_PATHS:
        report.error(os.path.basename(filepath) + ' has ' + str(len(rows)) + ' rows of parked cars, the game can load ' + str(MAX_PATHS)
                     + ': the last ' + str(len(rows) - MAX_PATHS) + ' are left out')
        rows = rows[:MAX_PATHS]
    routes = []
    for i, row in enumerate(rows):
        points, raw = get_path(row)
        routes.append(('PATH' + str(i), points, raw))
    write_routes(filepath, routes)
    print(str(len(routes)) + ' rows of parked cars exported to ' + os.path.basename(filepath))


def export_parked_cars(data, racesubfolder, cityname):
    rows = get_rows(data)
    city_rows = [r for r in rows if not r['owner']]
    main = racesubfolder + cityname + '_parkedcar.pathset'
    if city_rows:
        write_rows(main, city_rows)
    else:
        Path(main).unlink(missing_ok=True)

    names = []
    for race_id, race in races(data):
        owner = state_val(race, IDENTITY, '')
        owned = [r for r in rows if owner and r['owner'] == owner]
        if owned:
            # the rows of the race first: the last ones are the ones left out when there are too many
            name = cityname + '_parkedcar_' + race_id + '.pathset'
            write_rows(racesubfolder + name, owned + city_rows)
            names.append(name)

    # only the files written by a previous export are removed: the name of a file can't tell who made it
    manifest = racesubfolder + MANIFEST
    previous = []
    if os.path.exists(manifest):
        with open(manifest, encoding='utf-8') as stream:
            previous = json.load(stream)
    pattern = re.escape(cityname) + r'_parkedcar_(blitz|circuit|race)\d+\.pathset'
    for name in previous:
        if isinstance(name, str) and re.fullmatch(pattern, name) and name not in names:
            Path(racesubfolder + name).unlink(missing_ok=True)
    if names or previous:
        with open(manifest, 'w', encoding='utf-8') as stream:
            json.dump(names, stream)
