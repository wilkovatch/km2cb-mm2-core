from .scene_input import SceneInput
from .psdl_writer import PSDLWriter
from .inst_writer import INSTWriter
from .bai_writer import BAIWriter
from .pathset_writer import PATHSETWriter
from .decal_writer import DecalWriter
from .pkg_writer import PKGWriter
from . import report

class MainWriter:
    def __init__(self,
                 filepath,
                 scene_input: SceneInput,
                 write_psdl,
                 write_inst,
                 write_bai,
                 write_pathset,
                 write_pkgs,
                 split_non_coplanar_roads,
                 accurate_bai_culling,
                 cap_materials,
                 physics_map=None,
                 geometry_path=None,
                 bound_path=None):
        self.filepath = filepath
        self.scene_input = scene_input
        self.write_psdl = write_psdl
        self.write_inst = write_inst
        self.write_bai = write_bai
        self.write_pathset = write_pathset
        self.write_pkgs = write_pkgs
        self.split_non_coplanar_roads = split_non_coplanar_roads
        self.accurate_bai_culling = accurate_bai_culling
        self.cap_materials = cap_materials
        self.physics_map = physics_map
        # the folders of the PKG and bound files (see PKGWriter)
        self.geometry_path = geometry_path
        self.bound_path = bound_path

    # each file is written even if the ones before failed, when the errors are collected (see report.guarded)
    def write(self):
        if self.write_psdl:
            with report.guarded("the PSDL was not written"):
                writer = PSDLWriter(self.scene_input, self.filepath, self.split_non_coplanar_roads, self.cap_materials)
                writer.write()
        if self.write_inst:
            with report.guarded("the INST was not written"):
                writer = INSTWriter(self.scene_input, self.filepath)
                writer.write()
        if self.write_bai:
            with report.guarded("the BAI was not written"):
                writer = BAIWriter(self.scene_input, self.filepath, self.accurate_bai_culling)
                writer.write()
        if self.write_pathset:
            with report.guarded("the PATHSET was not written"):
                writer = PATHSETWriter(self.scene_input, self.filepath)
                writer.write()
            with report.guarded("the decals were not written"):
                rails = BAIWriter(self.scene_input, self.filepath, self.accurate_bai_culling).get_cable_car_rails()
                writer = DecalWriter(self.scene_input, self.filepath, rails)
                writer.write()
        if self.write_pkgs:
            with report.guarded("the PKGs were not written"):
                writer = PKGWriter(self.scene_input, self.filepath, self.physics_map, self.geometry_path, self.bound_path)
                writer.write()
