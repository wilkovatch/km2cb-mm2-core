import math
from pathlib import Path

from writers import report
from route_pathset import write_routes
from utils import state_val

# The boats, ducks, tugs and the car ferry of the city: a pathset in the race folder for each manager of the game
# (race/<city>/<city>_sailboat.pathset and <city>_ferry.pathset), with a line strip for each route. The path name is the
# model (geometry/<name>.pkg); the sailboat file uses the default model of the game for the names without a model.
# The route is a closed loop: the objects move along it for ever, from the last point back to the first one.
# Each entry is (pathset, model name or None, default speed in m/s), indexed by the "model" parameter.
MODELS = [
    ('sailboat', None, 5),
    ('sailboat', 'giz_sailboard01_f', 20),
    ('sailboat', 'giz_duck_s', 2),
    ('sailboat', 'giz_tug01_l', 5),
    ('sailboat', 'giz_watertaxi01_l', 5),
    ('ferry', 'giz_carferry01_l', 5),
]
PATHSETS = ['sailboat', 'ferry']
# the sailboat objects move at spacing / 4 m/s (+-1 m/s each), the spacing byte is not read for the ferry (stock: 20)
SPACING_PER_MS = 4
FERRY_SPACING = 20


def get_boat_routes(data):
    # Control points are the native input to MM2's own interpolation, never the editor's sampled preview.
    res = {name: [] for name in PATHSETS}
    for i, element in enumerate(data.get('customElements') or []):
        if element.get('type') != 'movingObject':
            continue
        element_data = element.get('data') or {}
        name = element_data.get('name') or ('boat ' + str(i + 1))
        state = (element_data.get('fields') or {}).get('state') or {}
        try:
            points = [tuple(p['position']) for p in (element.get('points') or {}).get('spline') or []]
            valid = all(len(p) == 3 and all(math.isfinite(c) for c in p) for p in points)
        except (KeyError, TypeError, ValueError):
            points, valid = [], False
        if not valid:
            report.warning('the boat route ' + name + ' has invalid points, it is not exported')
            continue
        if len(points) < 3:
            report.warning('the boat route ' + name + ' has less than three points, it is not exported')
            continue
        if any(a == b for a, b in zip(points, points[1:] + points[:1])):
            report.warning('the boat route ' + name + ' has invalid or zero-length spans, it is not exported')
            continue
        model = state_val(state, 'model', 0)
        if type(model) is not int or not 0 <= model < len(MODELS):
            report.warning('the boat route ' + name + ' has an unknown model, it is not exported')
            continue
        pathset, model_name, default_speed = MODELS[model]
        speed = state_val(state, 'speed', 0)
        if type(speed) not in (int, float) or not math.isfinite(speed) or speed < 0:
            report.warning('the boat route ' + name + ' has an invalid speed, the default of the model is used')
            speed = 0
        if pathset == 'ferry':
            spacing = FERRY_SPACING
        else:
            spacing = max(1, min(255, round((speed if speed > 0 else default_speed) * SPACING_PER_MS)))
        res[pathset].append((model_name, [(-p[0], p[1], p[2]) for p in points], spacing))
    return res


def export_boats(data, racesubfolder, cityname):
    routes = get_boat_routes(data)
    for pathset in PATHSETS:
        filepath = racesubfolder + cityname + '_' + pathset + '.pathset'
        if len(routes[pathset]) == 0:
            Path(filepath).unlink(missing_ok=True)
            continue
        write_routes(filepath, [(model_name or 'PATH' + str(i), points, spacing)
                                for i, (model_name, points, spacing) in enumerate(routes[pathset])])
        print(str(len(routes[pathset])) + ' ' + pathset + ' routes exported')
