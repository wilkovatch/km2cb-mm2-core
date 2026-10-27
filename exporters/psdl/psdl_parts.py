# The parts of the city as the PSDL writer reads them (written to the .bin file by BINExporter): each one is named
# "<prefix,><block>_<TYPE>" (ROADS, ROADSN, ROADN, ROADD, ROADDN, RAIL, RAILC, SW, CW, IS, BLOCK, ROOF, FAC, FACB, SLIVER,
# NUL, PKG, INST, PTH, BAI, TRAFL, DECAL), with its vertices, its triangles (used to find the perimeter of the block),
# its textures and the properties of its type. They are made from the procedural elements (json_processor.py) and from
# the low-level elements (low_level.py), and the converters make low-level elements from them.

import os


class ExportedCityElement:
    def __init__(self):
        self.is_mesh = False
        self.name = ''
        self.mat = ''
        self.properties = {}
        self.vertices = []
        self.indices = []
        self.normals = []
        self.uvs = []
        self.translation = (0, 0, 0)
        self.rotation = (0, 0, 0, 1)
        self.scale = (1, 1, 1)
        self.source = None  # the element of the city it comes from: (kind, id), not written to the .bin

    def part_type(self):
        return self.name.split(',')[-1].split('_')[1].split('.')[0]

    def block(self):
        return int(self.name.split(',')[-1].split('_')[0])

    def set_block(self, block):
        prefix = self.name.rsplit(',', 1)[0] + ',' if ',' in self.name else ''
        self.name = prefix + str(block) + '_' + self.part_type()


def get_tex(tex):
    # the name of a texture in the PSDL: the file name of its path ("NONE" if there is none)
    if tex is None or tex == '':
        return 'NONE'
    return tex.split('/')[-1]


def section_indices(i, n, section_index=0):
    i += section_index * n
    return [i, i + 1, i + 1 + n, i, i + 1 + n, i + n]


def section_indices_rev(i, n, section_index=0):
    i += section_index * n
    return [i + n, i + 1 + n, i, i + 1 + n, i + 1, i]


def strip_indices(num_sections, vertices_per_section, rev=True):
    # the triangles of a strip of sections of vertices_per_section vertices each (as the roads)
    res = []
    f = section_indices_rev if rev else section_indices
    for i in range(num_sections - 1):
        for j in range(vertices_per_section - 1):
            res.extend(f(j, vertices_per_section, i))
    return res


def texture_list(*textures):
    return ','.join(get_tex(t) for t in textures)
