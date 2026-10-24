import sys
import os
import traceback

sys.path.append(sys.argv[1])

import DecodeExportedJson
from json_processor import JsonProcessor
from bin_export import BINExporter
from prop_rules_export import PropRulesExporter
from cinfo_aimap_export import CinfoAimapExporter
from scene_input import StandaloneSceneInput
from common.main_writer import MainWriter

def parse_flag(i):
    return int(sys.argv[i]) > 0

def read_physics_map():
    # texture -> bound material, from the city/materials.csv of the game,
    # provided by the user in the common folder of the core (Files/common/MidtownMadness2/city)
    res = {}
    path = os.path.join(os.path.dirname(os.path.normpath(os.path.abspath(sys.argv[1]))), 'common', 'MidtownMadness2', 'city', 'materials.csv')
    if os.path.exists(path):
        with open(path, 'r') as f:
            for line in f.readlines()[1:]:
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    res[parts[0].lower()] = parts[1].strip()
    else:
        print("Warning: " + path + " not found (copy it from the city folder of the game), the PKG bounds will use the default material")
    return res

try:
    if len(sys.argv) != 16:
        raise Exception("Wrong number of arguments, must be 15 (modules path, input json file, output psdl file, and 12 flags), got " + str(len(sys.argv) - 1))
    # flag order (values are 0 or 1, first index is 4):
    # - write prop rules
    # - write bin only (will ignore the subsequent flags if set)
    # - write psdl
    # - write inst
    # - write bai
    # - write pathset
    # - write cinfo and aimap
    # - write pkgs (and bounds)
    # - split non coplanar roads
    # - accurate bai culling
    # - cap materials to 511
    # - verbose

    write_prop_rules = parse_flag(4)
    write_bin_only = parse_flag(5)
    write_psdl = parse_flag(6)
    write_inst = parse_flag(7)
    write_bai = parse_flag(8)
    write_pathset = parse_flag(9)
    write_cinfo_aimap = parse_flag(10)
    write_pkgs = parse_flag(11)
    split_non_coplanar_roads = parse_flag(12)
    accurate_bai_culling = parse_flag(13)
    cap_materials = parse_flag(14)
    verbose = parse_flag(15)

    psdl_file = sys.argv[3]
    bin_file = psdl_file.replace(".psdl", ".bin")

    # export BIN
    dj = DecodeExportedJson.DecodeExportedJson()
    data = dj.decode_json(sys.argv[2])
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
            accurate_bai_culling, cap_materials, read_physics_map()
        )
        writer.write()
        os.remove(bin_file)

    if write_prop_rules:
        prop_exp = PropRulesExporter(jp, verbose)
        prop_exp.export_props_rules(bin_file)

    if write_cinfo_aimap:
        cinfo_aimap_exp = CinfoAimapExporter(jp, verbose)
        cinfo_aimap_exp.export_cinfo_aimap(bin_file)

    input("Press any key to continue...")

except Exception:
    traceback.print_exc()
    input("Press any key to continue...")
