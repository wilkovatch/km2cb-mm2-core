import math

from .scene_input import SceneInput
from .file_io import BinaryFileHelper
from .utils import Utils
from .pkg_writer import PKGGroups
from . import report

# MM2 keeps the geometry of the objects in static tables of about 4096 slots, without checking the limit (midtown2.exe
# 0x4632c0): past it the game overwrites the variables after them and crashes while loading the objects (at 0x4a48d8).
# Each different object name takes 6 slots (the object and its shadow, mask, nonrandom, refl and opaque variants, used
# even if missing), the instances of the same object share them. Some slots are left to the props and vehicles
GEOMETRY_SLOTS = 4096
SLOTS_PER_OBJECT = 6
RESERVED_GEOMETRY_SLOTS = 512
MAX_OBJECTS = (GEOMETRY_SLOTS - RESERVED_GEOMETRY_SLOTS) // SLOTS_PER_OBJECT


class INSTWriter:
    def __init__(self, scene_input: SceneInput, filepath):
        self.scene_input = scene_input
        self.filepath = filepath
        self.utils = Utils(self.scene_input)

    def process_inst_elem(self, obj):
        rot = self.scene_input.get_rotation(obj)
        pr = self.scene_input.get_property_container(obj)
        scalex = self.scene_input.get_scale(obj)[0]
        scalez = self.scene_input.get_scale(obj)[2] #TODO: fix name (this is the vertical)
        scaley = self.scene_input.get_scale(obj)[1]
        origo = self.scene_input.get_position(obj)
        iblock = self.utils.get_block_number(obj)
        obj_name = pr["object"]
        flags = int(pr.get("flags", 0))
        axes = self.scene_input.get_instance_axes(obj) if hasattr(self.scene_input, "get_instance_axes") else None
        self.export_elem(rot, scalex, scaley, scalez, origo, iblock, obj_name, flags, axes)

    def process_pkg_group(self, group):
        # the pkg is in coordinates relative to its pivot, 256 = visible from every angle
        self.export_elem([0, 0, 0], 1, 1, 1, group.pivot, group.block, group.stem, 256)

    def export_elem(self, rot, scalex, scaley, scalez, origo, iblock, obj_name, flags, axes=None):
        file = self.file
        self.object_names.add(obj_name.lower())
        rx = rot[0]
        rz = rot[1]
        ry = rot[2]
        if ry == 0:
            ry = 0.0000000001  # else MM2 crashes for some reason
        ib = self.utils.get_real_block_number(self.blocks, iblock)
        file.write_uint16(ib + 1)
        file.write_uint16(flags)
        simple_axes = axes is not None and abs(axes[2][0] + axes[0][2]) < 1e-6 and abs(axes[2][2] - axes[0][0]) < 1e-6 and abs(axes[0][1]) < 1e-6 and abs(axes[2][1]) < 1e-6 and all(
            abs(a - b) < 1e-6 for a, b in zip(axes[1], (0, 1, 0))) and abs(sum(v*v for v in axes[0])-1) < 1e-6 and abs(sum(v*v for v in axes[2])-1) < 1e-6
        if simple_axes:
            file.write_byte(len(obj_name) + 129)
            file.write_zero_terminated_string(obj_name)
            file.write_float(axes[0][0])
            file.write_float(axes[0][2] if abs(axes[0][2]) > 1e-12 else -1e-10)
        elif axes is not None:
            file.write_byte(len(obj_name) + 1)
            file.write_zero_terminated_string(obj_name)
            for axis in axes:
                for value in axis:
                    file.write_float(value)
        elif (abs(1.0 - scalex) < 0.0001 and
            abs(1.0 - scaley) < 0.0001 and
            abs(1.0 - scalez) < 0.0001 and
            abs(rx) < 0.0002 and
                abs(rz) < 0.0002):
            file.write_byte(len(obj_name) + 129)
            file.write_zero_terminated_string(obj_name)
            file.write_float(math.cos(ry))
            file.write_float(-math.sin(ry))
        else:
            r11 = (math.cos(ry) * math.cos(rz) * scalex)
            r12 = (math.sin(rz) * scalex)
            r13 = (-math.sin(ry) * math.cos(rz) * scalex)
            r21 = (-math.cos(ry) * math.sin(rz) * scalez)
            r22 = (math.cos(rz) * scalez)
            r23 = (math.sin(ry) * math.sin(rz) * scalez)
            r31 = (math.sin(ry) * scaley)
            r32 = 0
            r33 = (math.cos(ry) * scaley)
            xaxis = [r11, r12, r13]
            yaxis = [r21, r22, r23]
            zaxis = [r31, r32, r33]
            file.write_byte(len(obj_name) + 1)
            file.write_zero_terminated_string(obj_name)
            file.write_float(xaxis[0])
            file.write_float(xaxis[1])
            file.write_float(xaxis[2])
            file.write_float(yaxis[0])
            file.write_float(yaxis[1])
            file.write_float(yaxis[2])
            file.write_float(zaxis[0])
            file.write_float(zaxis[1])
            file.write_float(zaxis[2])
        file.write_vec3(origo)

    def write(self):
        self.file = BinaryFileHelper(self.filepath.replace(".psdl", ".inst"), 'wb')
        self.blocks = self.utils.get_real_blocks()
        self.object_names = set()
        for obj in self.scene_input.get_object_list():
            typ = self.utils.get_object_type(obj)
            if typ == "INST":
                self.process_inst_elem(obj)
        for group in PKGGroups(self.scene_input, self.filepath).groups:
            self.process_pkg_group(group)
        self.file.close()
        if len(self.object_names) > MAX_OBJECTS:
            report.warning("the INST file has " + str(len(self.object_names)) + " different objects, more than "
                  + str(MAX_OBJECTS) + ": the game will likely crash while loading them (merge or reuse meshes, "
                  + "or export fewer elements to PKG)")
        print("INST exported!")
