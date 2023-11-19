import sys
import os
import traceback

sys.path.append(sys.argv[1])

import DecodeExportedJson
from bin_export import BINExporter
from scene_input import StandaloneSceneInput
from common.main_writer import MainWriter

try:
    if len(sys.argv) != 14:
        raise Exception("Wrong number of arguments, must be 13 (modules path, input json file, output psdl file, and 10 flags), got " + str(len(sys.argv)))
    # flag order (values are 0 or 1):
    # - write prop rules
    # - write bin only (will ignore the subsequent flags if set)
    # - write psdl
    # - write inst
    # - write bai
    # - write pathset
    # - split non coplanar roads
    # - cap materials to 511
    # - accurate bai culling
    # - verbose

    psdl_file = sys.argv[3]
    bin_file = psdl_file.replace(".psdl", ".bin")

    # export BIN
    dj = DecodeExportedJson.DecodeExportedJson()
    data = dj.decode_json(sys.argv[2])
    exp = BINExporter(data, int(sys.argv[12]) > 0)
    exp.export_bin_file(bin_file, sys.argv[4])

    if not int(sys.argv[5]):
        # not a bin only export
        scene_input = StandaloneSceneInput(bin_file)
        writer = MainWriter(psdl_file, scene_input, int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8]), int(sys.argv[9]), int(sys.argv[10]), int(sys.argv[11]), int(sys.argv[12]))
        writer.write()
        os.remove(bin_file)
    input("Press any key to continue...")

except Exception:
    traceback.print_exc()
    input("Press any key to continue...")
