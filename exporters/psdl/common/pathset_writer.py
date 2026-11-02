import math
import os
import numpy as np

from .scene_input import SceneInput
from .file_io import BinaryFileHelper
from .utils import Utils


class PATHSETWriter:
    def __init__(self, scene_input: SceneInput, filepath):
        self.scene_input = scene_input
        self.filepath = filepath
        self.utils = Utils(self.scene_input)

    def process_object(self, obj):
        pr = self.scene_input.get_property_container(obj)
        typ = self.utils.get_object_type(obj)
        if typ == "PTH":
            if pr["flags"] == "2":
                self.types.append(pr["object"] + ".2")
                self.totobjs.append([obj])
                return
            found = False
            object_and_flags = pr["object"] + "." + pr["flags"]
            for it in range(len(self.types)):
                if object_and_flags == self.types[it]:
                    print("prop found in temp list " + object_and_flags)
                    self.totobjs[it].append(obj)
                    found = True
                    break
            if not found:
                print("(not an error) prop not found in temp list " + object_and_flags)
                self.types.append(object_and_flags)
                newt = [obj]
                self.totobjs.append(newt)

    def write_elem(self, i):
        file = self.file
        object_and_flags = self.types[i].rsplit(".", 1)
        file.write_string32(object_and_flags[0])
        points = []
        typ = int(object_and_flags[1])
        if typ == 0:
            for obj in self.totobjs[i]:
                points.append(self.scene_input.get_position(obj))
        elif typ == 1:
            for obj in self.totobjs[i]:
                pos = self.scene_input.get_position(obj)
                points.append(pos)
                rot = self.scene_input.get_rotation(obj)
                rotpos = (math.cos(rot[2]), math.sin(rot[2]), 0)
                points.append(np.subtract(pos, rotpos))
        elif typ == 2:
            obj = self.totobjs[i][0]
            points = [self.scene_input.get_vertex(obj, j) for j in range(self.scene_input.get_vertices_num(obj))]
        file.write_uint32(len(points))
        file.write_uint32(0)
        for p in points:
            file.write_uint32(0)
            file.write_float(-p[0])
            file.write_float(p[2])
            file.write_float(p[1])
        file.write_byte(typ)
        file.write_byte(int(self.scene_input.get_property_container(self.totobjs[i][0]).get("spacing", 0)) if typ == 2 else 0)  # spacing
        file.write_uint16(0)

    def write(self, output_path=None, race=None):
        folder_path = self.filepath.replace(".psdl", "")
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        self.file = BinaryFileHelper(output_path or folder_path + "/props.pathset", 'wb')
        file = self.file
        self.types = []
        self.totobjs = []
        for obj in self.scene_input.get_object_list():
            if (self.scene_input.get_property_container(obj).get('race') or None) != race:
                continue
            self.process_object(obj)
        file.write_raw_string("PTH1")
        file.write_uint32(len(self.types))
        file.write_uint32(0)
        for i in range(len(self.types)):
            self.write_elem(i)
        file.close()
        print("PATHSET exported!")
