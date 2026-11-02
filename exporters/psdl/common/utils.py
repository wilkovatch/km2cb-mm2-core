from .scene_input import SceneInput
import numpy as np


class Utils:
    def __init__(self, scene_input: SceneInput):
        self.scene_input = scene_input

    def get_block_number(self, obj):
        obj_name = self.scene_input.get_object_name(obj)
        return int(obj_name.split(",")[-1].split("_")[0])

    def get_object_type(self, obj):
        obj_name = self.scene_input.get_object_name(obj)
        return obj_name.split(",")[-1].split("_")[1].split(".")[0]

    def get_real_blocks(self):
        blocks2 = []
        n_blocks = max(self.get_block_number(obj) for obj in self.scene_input.get_object_list())
        for i in range(n_blocks):
            blocks2.append([])
        for obj in self.scene_input.get_object_list():
            bname = self.get_object_type(obj)
            vert_num = self.scene_input.get_vertices_num(obj)
            poly_num = self.scene_input.get_polygons_num(obj)
            # as PSDLWriter.read_blocks (PERIM: a manual perimeter, without faces)
            has_geometry = bname not in ["INST", "BAI", "PTH", "PKG", "TRAFL"] and (bname == "RAIL" or (vert_num > 0 and poly_num > 0)
                                                                                  or (bname == "PERIM" and vert_num > 0))
            if has_geometry:
                n = self.get_block_number(obj)
                if n not in blocks2[n - 1]:
                    blocks2[n - 1].append(n)
        blocks = []
        for b in blocks2:
            if len(b) != 0:
                blocks.append(b)
        return blocks

    def get_real_block_number(self, blocks, iblock):
        for i in range(len(blocks)):
            if iblock == blocks[i][0]:
                return i
        return -1

    def get_normal(self, v):
        return v / np.linalg.norm(v)
