"""Native movable bridges: fixed-size leaves, not moving-object spline routes or ordinary props."""
import json
import math
import os
import re
import shutil
import sys
from pathlib import Path

from writers import report
from writers.pathset_writer import MAX_PATHS
from prop_placers import model_name
from race_elements import races, IDENTITY, OWNER
from route_pathset import write_routes
from utils import state_val

DEFAULT_MESH = 'geometry/giz_bridge01_l.pkg'
# the textures of the generated models, as the stock bridges (see converters/generateBridgeMesh)
DEFAULT_TRUSS_TEXTURE, DEFAULT_BOTTOM_TEXTURE, DEFAULT_RAIL_TEXTURE = 'tl_bridgetruss_side_l', 'tl_bridgetruss_bot_l', 'tl_bridgetrim_l'
STOCK_MODELS = ('giz_bridge01_l', 'giz_waterloo_l', 'giz_bridge02_l')  # with their banger data in the game, imported or not
PREFIXES = ('time:', 'prox:', 'inactive:', 'open:')
MAX_NAME = 32
MANIFEST = '.km2-bridge-races.json'
TUNING_MANIFEST = '.km2-bridge-tuning.json'  # the banger data written here, the only files overwritten

# The fields of a dgBangerData file, as in the stock ones. A bridge without one crashes the game (see generated_tuning).
TUNING = '''type: a
dgBangerData {{
  AudioId 0
  Size {x:f}\t{y:f}\t{z:f}
  CG 0.000000\t0.000000\t0.000000
  NumGlows 0
  Mass {mass:f}
  Elasticity 0.500000
  Friction 0.900000
  ImpulseLimit2 1.0e+30
  SpinAxis 0
  Flash 0
  NumParts 0
  BirthRule {{
    Position 0.000000\t0.000000\t0.000000
    PositionVar 0.000000\t0.000000\t0.000000
    Velocity 0.000000\t0.000000\t0.000000
    VelocityVar 0.000000\t0.000000\t0.000000
    Life 1.000000
    Mass 1.000000
    MassVar 0.000000
    Radius 1.000000
    RadiusVar 0.000000
    Drag 0.000000
    DragVar 0.000000
    DRadius 0.000000
    DRadiusVar 0.000000
    DAlpha 0
    DAlphaVar 0
    DRotation 0
    DRotationVar 0
    InitialBlast 0
    SpewRate 0.000000
    SpewTimeLimit 0.000000
    Gravity -9.800000
    TexFrameStart 0
    TexFrameEnd 0
    BirthFlags 0
    }}
  TexNumber 0
  BillFlags 0
  YRadius {radius:f}
  ColliderId 0
  CollisionPrim 0
  CollisionType 48
}}
'''


def find_file(folder, name):
    # the file names of the game have any case
    folder = Path(folder)
    if not folder.is_dir():
        return None
    return next((entry for entry in folder.iterdir() if entry.name.lower() == name.lower()), None)


def pkg_size(path):
    # the size of the model, as the Size of the stock banger data
    server = str(Path(__file__).resolve().parents[2] / 'server')
    if server not in sys.path:
        sys.path.append(server)
    import mesh_formats
    objects = []
    f = mesh_formats.BinaryFileHelper(str(path), 'rb')
    try:
        header = f.read_bytes(4)
        if header not in (b'PKG2', b'PKG3'):
            raise ValueError('not a PKG file')
        length = os.path.getsize(path)
        while not mesh_formats.reached_end(f, length):
            mesh_formats.read_pkg_file(f, header, [], objects)
    finally:
        f.close()
    vertices = [v for o in objects for v in o.get('vertices', [])]
    if not vertices:
        raise ValueError('the model has no vertices')
    return [max(v[i] for v in vertices) - min(v[i] for v in vertices) for i in range(3)]


def generated_tuning(size):
    # the density of the stock bridges (the mass only matters when something pushes the leaf); the bound of the file
    # <model>_bound is optional, without it the collision is a box of this Size (CollisionPrim 0, 4411c0)
    x, y, z = size
    return TUNING.format(x=x, y=y, z=z, mass=x * y * z * 800, radius=math.hypot(x, z) * 0.5)


def write_tuning(folder, generated):
    # writes the banger data generated for the custom models, and removes the ones not needed anymore
    manifest = folder / TUNING_MANIFEST
    previous = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else []
    for name, text in generated.items():
        path = folder / name
        if path.exists() and name not in previous:
            report.warning(name + ' is already in the export folder and was kept: the size of the bridge model comes from it')
            continue
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='ascii', newline='\n')
    for name in previous:
        if isinstance(name, str) and name not in generated and Path(name).name == name:
            (folder / name).unlink(missing_ok=True)
    if generated or previous:
        folder.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(sorted(generated)), encoding='utf-8')


def copy_to(source, folder):
    # to the folder of the export, which can be the one of the file
    target = folder / source.name
    if target.exists() and target.samefile(source):
        return
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def copy_city_model(model, data, tune_folder):
    # a model in the folder of the city goes with the export, as its banger data, to be there also without an AR file
    city = data.get('cityFolder')
    if not city:
        return
    root = tune_folder.parents[1]
    for subfolder, name in (('geometry', model + '.pkg'), ('bound', model + '_BOUND.bnd')):
        source = find_file(Path(city) / subfolder, name)
        if source:
            copy_to(source, root / subfolder)


def ensure_tuning(model, data, common_dir, tune_folder, generated):
    # gizBridge::UpdateMatrix (577620) reads Size from the banger data of the model without checking it, and the banger data
    # manager (440940) gives no entry for a model without a file: the game would crash with a bridge using that model.
    # Raises ValueError if the file can't be provided
    if model in STOCK_MODELS:
        return
    name = model + '.dgBangerData'
    if common_dir and find_file(Path(common_dir) / 'tune' / 'banger', name):
        return  # a file of the game
    city = data.get('cityFolder')
    custom = find_file(Path(city) / 'tune' / 'banger', name) if city else None
    if custom:
        # the archive only gets the geometry and texture folders of the city
        copy_to(custom, tune_folder)
        return
    for root in (city, common_dir):
        path = find_file(Path(root) / 'geometry', model + '.pkg') if root else None
        if path:
            generated[name] = generated_tuning(pkg_size(path))
            return
    raise ValueError('its model ' + model + '.pkg was not found')


def get_bridges(data, common_dir=None, tune_folder=None, generated=None):
    result = []
    elements = data.get('customElements') or []
    owners = {state_val(race, IDENTITY, '') for _, race in races(data)} - {''}
    for element in elements:
        if element.get('type') != 'bridge':
            continue
        name = element['data']['name']
        state = element['data']['fields']['state']
        try:
            a, b = [tuple(element['points'][key]['position']) for key in ('start', 'finish')]
            if any(len(p) != 3 or any(type(c) not in (int, float) or not math.isfinite(c) or abs(c) > 1e30 for c in p) for p in (a, b)):
                raise ValueError('invalid placement points')
            if math.hypot(a[0] - b[0], a[2] - b[2]) < 0.001:
                raise ValueError('the placement points need different horizontal positions')
            mesh, behavior = state_val(state, 'mesh') or DEFAULT_MESH, state_val(state, 'behavior', 0)
            if not isinstance(mesh, str) or not mesh.lower().endswith('.pkg'):
                raise ValueError('the model must be a PKG file')
            if type(behavior) is not int or not 0 <= behavior < len(PREFIXES):
                raise ValueError('unknown behavior')
            model = model_name(mesh)
            # the game splits the name at the colon and at the at sign (577e30)
            if not model.isascii() or re.search('[:@]', model) or len(PREFIXES[behavior] + model) > MAX_NAME:
                raise ValueError('the name of the model must be ASCII, without : and @, and at most ' + str(MAX_NAME - len(PREFIXES[behavior])) + ' characters long')
            paired = state_val(state, 'paired', True)
            if type(paired) is not bool:
                raise ValueError('invalid paired-leaf setting')
            owner = state_val(state, OWNER, '')
            if owner and owner not in owners:
                raise ValueError('unknown race container')
            replaces = state_val(state, 'replaces')
            replacement = None
            if replaces:
                if not owner:
                    raise ValueError('only a race-owned bridge can replace a city bridge')
                if not isinstance(replaces, dict) or replaces.get('kind') != 'customElement' or type(replaces.get('id')) is not int:
                    raise ValueError('invalid city bridge reference')
                target = next((e for e in elements if e.get('id') == replaces.get('id')), None)
                if target is None or target.get('type') != 'bridge' or state_val(target['data']['fields']['state'], OWNER, ''):
                    raise ValueError('the replacement target must be a city bridge')
                replacement = target['id']
            if tune_folder is not None:
                ensure_tuning(model, data, common_dir, tune_folder, generated)
                copy_city_model(model, data, tune_folder)
            if abs(a[1] - b[1]) > 0.001:
                report.warning('the bridge ' + name + ' has unequal control heights: MM2 distorts sloped bridge frames, while the editor shows a rigid model',
                               element=name, kind='customElement')
            if mesh == state_val(state, 'generatedMesh'):
                length = math.hypot(a[0] - b[0], a[2] - b[2]) * (0.5 if paired else 1)
                if abs(length - float(state_val(state, 'generatedLength', 0) or 0)) > 0.01:
                    report.warning('the model of the bridge ' + name + ' was generated for another distance of its hinges: generate it again',
                                   element=name, kind='customElement')
            points = [a, tuple((a[i] + b[i]) * 0.5 for i in range(3)), b] if paired else [a, b]
            result.append(dict(id=element['id'], owner=owner, replaces=replacement, name=name,
                               route=(PREFIXES[behavior] + model, [(-p[0], p[1], p[2]) for p in points], 20)))
        except (KeyError, TypeError, ValueError, OverflowError, OSError, IndexError) as error:
            report.error('the bridge ' + name + ' is not exported: ' + str(error), element=name, kind='customElement')
    return result


def write_bridges(path, bridges):
    if len(bridges) > MAX_PATHS:
        report.error(path.name + ' has more than ' + str(MAX_PATHS) + ' bridges; the remaining bridges are left out')
    write_routes(str(path), [b['route'] for b in bridges[:MAX_PATHS]])
    print(str(min(len(bridges), MAX_PATHS)) + ' bridges exported to ' + path.name)


def export_bridges(data, racesubfolder, cityname, common_dir=None):
    folder = Path(racesubfolder)
    tune_folder = folder.parents[1] / 'tune' / 'banger'  # <root>/race/<city>, see output_layout.py
    generated = {}
    bridges = get_bridges(data, common_dir, tune_folder, generated)
    write_tuning(tune_folder, generated)
    city = [b for b in bridges if not b['owner']]
    main = folder / (cityname + '_bridge.pathset')
    if city:
        write_bridges(main, city)
    else:
        main.unlink(missing_ok=True)
    names = []
    for race_id, race in races(data):
        owner = state_val(race, IDENTITY, '')
        owned = [b for b in bridges if owner and b['owner'] == owner]
        if not owned:
            continue
        replaced = [b['replaces'] for b in owned if b['replaces'] is not None]
        if len(set(replaced)) != len(replaced):
            report.error('more than one bridge replaces the same city bridge in ' + race_id)
            continue
        name = cityname + '_bridge_' + race_id + '.pathset'
        # A race PATHSET replaces the complete city file. Keep every city bridge that wasn't replaced.
        write_bridges(folder / name, owned + [b for b in city if b['id'] not in replaced])
        names.append(name)
    manifest = folder / MANIFEST
    previous = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else []
    pattern = re.escape(cityname) + r'_bridge_(blitz|circuit|race)\d+\.pathset'
    for name in previous:
        if isinstance(name, str) and re.fullmatch(pattern, name) and name not in names:
            (folder / name).unlink(missing_ok=True)
    if names or previous:
        temporary = manifest.with_suffix('.tmp')
        temporary.write_text(json.dumps(names), encoding='utf-8')
        temporary.replace(manifest)
