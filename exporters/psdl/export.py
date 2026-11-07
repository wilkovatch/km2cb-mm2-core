# The PSDL exporter of the Midtown Madness 2 core: writes the city (the export JSON of the program) as the files of the
# game, as in its folder (see output_layout.py), or packed in an .ar archive. The arguments are described in
# options.py, the structure of the exporter in docs/exporter.md of the core.

import sys
import os
import shutil
import tempfile
import traceback

sys.path.append(sys.argv[1])

import DecodeExportedJson
from options import ExportOptions
from json_processor import JsonProcessor
from scene import Scene
from prop_rules_export import PropRulesExporter
from cinfo_aimap_export import CinfoAimapExporter
from train_export import export_trains
from boat_export import export_boats
from bridge_export import export_bridges
from parked_car_export import export_parked_cars
from generated_export import GeneratedExport
from output_layout import OutputLayout
from ar_packer import ArPacker
from utils import state_bool
from writers.psdl_writer import PSDLWriter
from writers.inst_writer import INSTWriter
from writers.bai_writer import BAIWriter
from writers.pathset_writer import PATHSETWriter
from writers.decal_writer import DecalWriter
from writers.pkg_writer import PKGWriter
from writers import report

try:
    # the warnings and errors read back by the program (Files/python/ExportReport.py), missing in older versions
    import ExportReport
except ImportError:
    ExportReport = None


def wait_for_exit():
    # Linux may inherit closed or redirected stdin even when the editor runs in a console.
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            input("Press any key to continue...")
        except EOFError:
            pass


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


class Exporter:
    def __init__(self, options, layout):
        self.options = options
        self.layout = layout
        self.verbose = options['verbose']

    def read_city(self):
        data = DecodeExportedJson.DecodeExportedJson().decode_json(self.options.input_json)
        if ExportReport is not None:
            ExportReport.init(data)
        from race_elements import validate_ownership
        validate_ownership(data)
        self.data = data
        # the generated files first: their paths go in the data, read by the writers as the other files
        self.generated = GeneratedExport(self.layout.root, data, get_common_dir())
        if self.options['psdl']:
            with report.guarded("the low LOD textures were not generated"):
                self.generated.lod_textures()
        if self.options['pathset']:
            with report.guarded("the bridge models were not generated"):
                self.generated.bridge_models()
        self.physics_map = read_physics_map()
        self.jp = JsonProcessor(data, self.verbose)
        self.scene = Scene(self.jp.get_objects())

    def write_city_files(self):
        # the files made from the parts of the city, each one written even if the ones before failed, when the errors
        # are collected (see report.guarded)
        o = self.options
        psdl = self.layout.psdl
        if o['psdl']:
            with report.guarded("the PSDL was not written"):
                PSDLWriter(self.scene, psdl, o['psdl_splitNonCoplanarRoads'], o['psdl_capMaterials'],
                           state_bool(self.data.get('cityProperties'), 'assumeMM2Hook')).write()
        if o['inst']:
            with report.guarded("the INST was not written"):
                INSTWriter(self.scene, psdl).write()
        if o['bai']:
            with report.guarded("the BAI was not written"):
                if self.jp.network is None:
                    raise Exception("the traffic was not exported")
                BAIWriter(self.scene, self.jp.network, psdl, o['bai_accurateCulling']).write()
        if o['pathset']:
            with report.guarded("the PATHSET was not written"):
                PATHSETWriter(self.scene, psdl).write()
            with report.guarded("the decals were not written"):
                DecalWriter(self.scene, psdl).write()
        if o['pkgs']:
            with report.guarded("the PKGs were not written"):
                PKGWriter(self.scene, psdl, self.physics_map, self.layout.path('geometry'), self.layout.path('bound')).write()
        if o['pathset']:
            with report.guarded("the race props were not written"):
                from race_elements import write_props
                write_props(self.scene, self.data, self.layout)

    def write_other_files(self):
        o = self.options
        if o['propRules']:
            with report.guarded("the prop rules were not written"):
                PropRulesExporter(self.jp, self.verbose).export_props_rules(self.layout.psdl)

        if o['pathset']:
            # These are PATHSET files too; CINFO/AIMAP need not be selected to refresh them.
            for label, export_paths in [('trains', export_trains), ('boats', export_boats),
                                        ('bridges', lambda *args: export_bridges(*args, get_common_dir())),
                                        ('parked cars', export_parked_cars)]:
                with report.guarded('the ' + label + ' were not written'):
                    export_paths(self.data, self.layout.dir('race'), self.layout.city_name)

        if o['cinfo_aimap']:
            with report.guarded("the CINFO and AIMAP files were not written"):
                CinfoAimapExporter(self.jp, self.verbose).export_cinfo_aimap(self.layout)

        if o['hudmap']:
            try:
                import PIL
            except ImportError:
                PIL = None
                report.warning("the hudmap and the race maps need the Python module Pillow (PIL), install the requirements of the core to export them")
            if PIL is not None:
                with report.guarded("the hudmap was not written"):
                    from hudmap_export import HudmapExporter
                    HudmapExporter(self.jp, self.layout, self.physics_map, get_common_dir(), self.verbose).export()


def main():
    options = ExportOptions.from_argv(sys.argv)
    # the files are written as in the game folder (the PSDL in a city folder, see output_layout.py),
    # in a temporary folder when they are packed in an .ar file
    chosen = os.path.abspath(options.output)
    staging = None
    try:
        if options['packAr']:
            ar_file = os.path.splitext(chosen)[0] + ".ar"
            staging = tempfile.mkdtemp(prefix='km2_ar_')
            layout = OutputLayout(os.path.join(staging, os.path.splitext(os.path.basename(chosen))[0] + ".psdl"))
        else:
            layout = OutputLayout(chosen)
        layout.dir('city')

        exporter = Exporter(options, layout)
        exporter.read_city()
        exporter.write_city_files()
        exporter.write_other_files()
        with report.guarded("the list of the generated files was not written"):
            exporter.generated.finish()

        if options['packAr']:
            ArPacker(layout, exporter.data.get('cityFolder'), exporter.verbose).pack(ar_file)
            # the files in the root are not packed (the hudmap preview): they go next to the archive
            for name in os.listdir(layout.root):
                path = os.path.join(layout.root, name)
                if os.path.isfile(path):
                    shutil.move(path, os.path.join(os.path.dirname(ar_file), name))
            print("Exported to " + ar_file)
        else:
            print("Exported to " + layout.root)
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


try:
    main()
    wait_for_exit()
except Exception:
    traceback.print_exc()
    if ExportReport is not None:
        ExportReport.exception("the export failed")
    wait_for_exit()
    sys.exit(1)

# the errors collected along the way (see writers/report.py) fail the export
if report.has_errors():
    sys.exit(1)
