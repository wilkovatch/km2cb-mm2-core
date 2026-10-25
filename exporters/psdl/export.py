import sys
import os
import shutil
import tempfile
import traceback

sys.path.append(sys.argv[1])

import DecodeExportedJson
from json_processor import JsonProcessor
from bin_export import BINExporter
from prop_rules_export import PropRulesExporter
from cinfo_aimap_export import CinfoAimapExporter
from scene_input import StandaloneSceneInput
from output_layout import OutputLayout
from ar_packer import ArPacker
from common.main_writer import MainWriter
from common import report

try:
    # the warnings and errors read back by the program (Files/python/ExportReport.py), missing in older versions
    import ExportReport
except ImportError:
    ExportReport = None

def parse_flag(i):
    return int(sys.argv[i]) > 0

def get_common_dir():
    # the folder of the files of the game provided by the user (Files/common/MidtownMadness2)
    return os.path.join(os.path.dirname(os.path.normpath(os.path.abspath(sys.argv[1]))), 'common', 'MidtownMadness2')

def read_physics_map():
    # texture -> bound material, from the city/materials.csv of the game,
    # provided by the user in the common folder of the core (Files/common/MidtownMadness2/city)
    res = {}
    path = os.path.join(get_common_dir(), 'city', 'materials.csv')
    if os.path.exists(path):
        with open(path, 'r') as f:
            for line in f.readlines()[1:]:
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    res[parts[0].lower()] = parts[1].strip()
    else:
        report.warning(path + " not found (copy it from the city folder of the game), the PKG bounds will use the default material")
    return res

staging = None
try:
    if len(sys.argv) != 18:
        raise Exception("Wrong number of arguments, must be 17 (modules path, input json file, output psdl or ar file, and 14 flags), got " + str(len(sys.argv) - 1))
    # flag order (values are 0 or 1, first index is 4):
    # - write prop rules
    # - write bin only (will ignore the subsequent flags if set)
    # - write psdl
    # - write inst
    # - write bai
    # - write pathset
    # - write cinfo and aimap
    # - write hudmap and race map images
    # - write pkgs (and bounds)
    # - split non coplanar roads
    # - accurate bai culling
    # - cap materials to 511
    # - verbose
    # - pack to .ar (set when the chosen file is an .ar)

    write_prop_rules = parse_flag(4)
    write_bin_only = parse_flag(5)
    write_psdl = parse_flag(6)
    write_inst = parse_flag(7)
    write_bai = parse_flag(8)
    write_pathset = parse_flag(9)
    write_cinfo_aimap = parse_flag(10)
    write_hudmap = parse_flag(11)
    write_pkgs = parse_flag(12)
    split_non_coplanar_roads = parse_flag(13)
    accurate_bai_culling = parse_flag(14)
    cap_materials = parse_flag(15)
    verbose = parse_flag(16)
    pack_ar = parse_flag(17) and not write_bin_only

    # the files are written as in the game folder (the PSDL in a city folder, see output_layout.py),
    # in a temporary folder when they are packed in an .ar file
    chosen = os.path.abspath(sys.argv[3])
    if pack_ar:
        ar_file = os.path.splitext(chosen)[0] + ".ar"
        staging = tempfile.mkdtemp(prefix='km2_ar_')
        layout = OutputLayout(os.path.join(staging, os.path.splitext(os.path.basename(chosen))[0] + ".psdl"))
    else:
        layout = OutputLayout(chosen)
    layout.dir('city')
    psdl_file = layout.psdl
    bin_file = os.path.splitext(psdl_file)[0] + ".bin"

    # export BIN
    dj = DecodeExportedJson.DecodeExportedJson()
    data = dj.decode_json(sys.argv[2])
    if ExportReport is not None:
        ExportReport.init(data)
    physics_map = read_physics_map()
    jp = JsonProcessor(data, verbose)
    jp.get_objects()
    bin_exp = BINExporter(jp, verbose)
    bin_exp.export_bin_file(bin_file)

    if not write_bin_only:
        # not a bin only export
        scene_input = StandaloneSceneInput(bin_file)
        writer = MainWriter(
            psdl_file, scene_input, write_psdl, write_inst, write_bai,
            write_pathset, write_pkgs, split_non_coplanar_roads,
            accurate_bai_culling, cap_materials, physics_map,
            layout.path('geometry'), layout.path('bound')
        )
        writer.write()
        os.remove(bin_file)

    # the other files are written even if one fails, when the errors are collected (see common/report.py)
    if write_prop_rules:
        with report.guarded("the prop rules were not written"):
            prop_exp = PropRulesExporter(jp, verbose)
            prop_exp.export_props_rules(bin_file)

    if write_cinfo_aimap:
        with report.guarded("the CINFO and AIMAP files were not written"):
            cinfo_aimap_exp = CinfoAimapExporter(jp, verbose)
            cinfo_aimap_exp.export_cinfo_aimap(layout)

    if write_hudmap:
        try:
            import PIL
        except ImportError:
            PIL = None
            report.warning("the hudmap and the race maps need the Python module Pillow (PIL), install the requirements of the core to export them")
        if PIL is not None:
            with report.guarded("the hudmap was not written"):
                from hudmap_export import HudmapExporter
                HudmapExporter(jp, layout, physics_map, get_common_dir(), verbose).export()

    if pack_ar:
        ArPacker(layout, data.get('cityFolder'), verbose).pack(ar_file)
        # the files in the root are not packed (the hudmap preview): they go next to the archive
        for name in os.listdir(layout.root):
            path = os.path.join(layout.root, name)
            if os.path.isfile(path):
                shutil.move(path, os.path.join(os.path.dirname(ar_file), name))
        print("Exported to " + ar_file)
    else:
        print("Exported to " + layout.root)

    input("Press any key to continue...")

except Exception:
    traceback.print_exc()
    if ExportReport is not None:
        ExportReport.exception("the export failed")
    input("Press any key to continue...")
    sys.exit(1)

finally:
    if staging is not None:
        shutil.rmtree(staging, ignore_errors=True)

# the errors collected along the way (see common/report.py) fail the export
if report.has_errors():
    sys.exit(1)
