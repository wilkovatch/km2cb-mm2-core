# Transforms of the meshes from their placement point (used where the placement rules have meshTransform): the game draws
# a banger (prop) with the origin of its meshes at its centre of gravity, the CG of tune/banger/<pkg>.dgBangerData (as the
# props of the pathsets, of the prop rules and the traffic lights), a banger without banger data at its position. The
# editor puts a mesh without banger data on its lowest point instead (no transform, so autoYOffset applies).
import os

BANGER_FOLDER = os.path.join('tune', 'banger')
EXTENSION = '.dgbangerdata'

# the folder of the files of the game provided by the user (Files/common/MidtownMadness2)
COMMON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                          'common', 'MidtownMadness2')

# folder -> (modification time, lower case file name -> file name), the file names of the game have any case
_entries = {}


def find_file(folder, name):
    time = os.path.getmtime(folder)
    cached = _entries.get(folder)
    if cached is None or cached[0] != time:
        cached = (time, {e.lower(): e for e in os.listdir(folder)})
        _entries[folder] = cached
    entry = cached[1].get(name.lower())
    return os.path.join(folder, entry) if entry is not None else None


def banger_folders(path):
    # the tune/banger folder next to the geometry folder of the mesh (in the city's or the common folder), then the common one
    res = []
    for root in (os.path.dirname(os.path.dirname(os.path.abspath(path))), COMMON_DIR):
        folder = os.path.normcase(os.path.normpath(os.path.join(root, BANGER_FOLDER)))
        if os.path.isdir(folder) and folder not in res:
            res.append(folder)
    return res


def read_cg(path):
    # the CG of a dgBangerData file (a "dgBangerData { }" block of "Tag values" lines), None if it has none
    depth = 0
    with open(path, 'r', encoding='latin-1') as f:
        for line in f:
            t = line.split()
            if len(t) == 0:
                continue
            if t[-1] == '{':
                depth += 1
            elif t[0] == '}':
                depth -= 1
            elif depth == 1 and t[0] == 'CG' and len(t) >= 4:  # not the tags of the nested blocks (BirthRule)
                try:
                    return [float(v) for v in t[1:4]]
                except ValueError:
                    return None
    return None


def read_transform(path):
    folders = banger_folders(path)
    if len(folders) == 0:
        return {'warning': 'The banger data of the game (tune/banger/*.dgBangerData) is not in ' + COMMON_DIR + ', so the props '
                           'are put on their lowest point instead of where the game draws them: put the tune folder of the game there'}
    name = os.path.splitext(os.path.basename(path))[0] + EXTENSION
    for folder in folders:
        file = find_file(folder, name)
        if file is not None:
            cg = read_cg(file) or [0.0, 0.0, 0.0]  # the CG of default.dgBangerData (0)
            return {'position': [-cg[0], cg[1], cg[2]]}  # the x axis is mirrored, as in mesh_formats
    return None  # no banger data (e.g. a custom prop): put on its lowest point (autoYOffset)
