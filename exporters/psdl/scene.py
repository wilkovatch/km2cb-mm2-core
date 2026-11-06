# The parts of the city as the writers read them (see docs/exporter.md in the core): the ExportedCityElement made by
# json_processor.py (in the coordinates of the program) converted once to the space of the writers, which is the one
# of the program with y and z exchanged (x, z, y: z up, x not mirrored; the writers mirror x when writing the files).
# The conversion keeps what the writers were made for when they read the parts from an intermediate file:
# - the triangles are reversed (exchanging y and z mirrors them, reversing them restores their winding), the whole list
#   for the surfaces (also reversing their order, which the perimeter tracer follows), each submesh for the meshes;
# - the positions are rounded to 32 bit floats, as in the game files;
# - the textures are the properties texture0..N, before the own properties of the part (all strings);
# - the parts are sorted by name, keeping their order otherwise: the order of the INST objects, of the PATHSET types,
#   of the PKG groups and of the facades in the PSDL follows from it.

import numpy as np

from psdl_parts import ExportedCityElement


def to_writer_space(v):
    # a vector of the program as a vector of the writers, rounded to 32 bit floats (python floats)
    return tuple(float(c) for c in np.array((v[0], v[2], v[1]), dtype=np.float32))


def to_writer_rotation(r):
    # a rotation of the program (quaternion x, y, z, w) as the quaternion (w, x, y, z) of the space of the writers,
    # rounded to 32 bit floats
    return tuple(float(c) for c in np.array((-r[3], r[0], r[2], r[1]), dtype=np.float32))


def euler(q):
    # the Euler angles (x, y, z) of a quaternion (w, x, y, z) of the space of the writers (z is the heading)
    rx = np.arctan2(2 * (q[0] * q[1] + q[2] * q[3]), 1 - 2 * (q[1] * q[1] + q[2] * q[2]))
    ry = np.arcsin(np.clip(2 * (q[0] * q[2] - q[3] * q[1]), -1, 1))
    rz = np.arctan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] * q[2] + q[3] * q[3]))
    return [rx, ry, rz]


def triangle(indices, f):
    return indices[f * 3:(f + 1) * 3]


class Mesh:
    # vertices (tuples) and triangles (a flat list of indices); the PSDL writer composes the parts of a block in one
    def __init__(self, vertices=None, indices=None):
        self.vertices = vertices if vertices is not None else []
        self.indices = indices if indices is not None else []

    def num_triangles(self):
        return len(self.indices) // 3

    def triangle(self, f):
        return triangle(self.indices, f)

    def append_part(self, part):
        # adds the triangles of a part, returns a copy of it as a mesh
        copy = Mesh(list(part.vertices), list(part.indices))
        offset = len(self.vertices)
        self.vertices = self.vertices + copy.vertices
        self.indices = self.indices + [offset + i for i in copy.indices]
        return copy

    def remove_doubles(self, epsilon):
        # merges the vertices closer than epsilon (to the first one found) and drops the triangles left without area
        new_verts = []
        indices_map = {}
        for i in range(len(self.vertices)):
            v = self.vertices[i]
            found = -1
            for j in range(len(new_verts)):
                if np.linalg.norm(np.subtract(v, new_verts[j])) < epsilon:
                    found = j
                    break
            if found >= 0:
                indices_map[i] = found
            else:
                new_verts.append(v)
                indices_map[i] = len(new_verts) - 1
        new_indices = []
        for i in range(0, len(self.indices), 3):
            i0 = indices_map[self.indices[i]]
            i1 = indices_map[self.indices[i + 1]]
            i2 = indices_map[self.indices[i + 2]]
            if not (i0 == i1 or i1 == i2 or i2 == i0):
                new_indices.extend((i0, i1, i2))
        self.vertices = new_verts
        self.indices = new_indices


def rotation_matrix(q):
    # the 3x3 matrix of a quaternion (w, x, y, z)
    return np.array([
        [2 * (q[0] * q[0] + q[1] * q[1]) - 1, 2 * (q[1] * q[2] - q[0] * q[3]), 2 * (q[1] * q[3] + q[0] * q[2])],
        [2 * (q[1] * q[2] + q[0] * q[3]), 2 * (q[0] * q[0] + q[2] * q[2]) - 1, 2 * (q[2] * q[3] - q[0] * q[1])],
        [2 * (q[1] * q[3] - q[0] * q[2]), 2 * (q[2] * q[3] + q[0] * q[1]), 2 * (q[0] * q[0] + q[3] * q[3]) - 1]])


class ScenePart(Mesh):
    def __init__(self, element: ExportedCityElement):
        name = element.name
        last = name.split(',')[-1]
        self.name = name
        self.block = int(last.split('_')[0])  # the room (block) number, 0 for the parts outside of the rooms
        self.type = last.split('_')[1].split('.')[0]
        self.is_mesh = bool(element.is_mesh)
        self.source = element.source
        # the transform, in the space of the writers
        self.position = to_writer_space(element.translation)
        self.scale = to_writer_space(element.scale)
        self.rotation = to_writer_rotation(element.rotation)
        self.properties = {}
        for i, tex in enumerate(element.mat.split(',')):
            self.properties['texture' + str(i)] = tex
        self.properties.update(element.properties)
        matrix = self.transform_matrix()
        vertices = [to_writer_space(v) for v in element.vertices]
        self.vertices = [tuple(np.dot(matrix, (v[0], v[1], v[2], 1))[:3]) for v in vertices]
        if self.is_mesh:
            self.submeshes = [list(reversed(s)) for s in element.indices]
            self.normals = [to_writer_space(n) for n in element.normals]
            self.uvs = [tuple(float(c) for c in np.array(uv, dtype=np.float32)) for uv in element.uvs]
            self.indices = []
        else:
            self.indices = list(reversed(element.indices))

    def transform_matrix(self):
        t = np.identity(4)
        t[:3, 3] = self.position
        r = np.identity(4)
        r[:3, :3] = rotation_matrix(self.rotation)
        s = np.diag((self.scale[0], self.scale[1], self.scale[2], 1.0))
        return np.matmul(np.matmul(t, r), s)

    def euler(self):
        return euler(self.rotation)

    def axes(self):
        # the axes of an instance in the game (x mirrored, y up): the rows of its rotation and scale
        basis = rotation_matrix(self.rotation) @ np.diag(self.scale)
        conversion = np.array([[-1, 0, 0], [0, 0, 1], [0, 1, 0]], dtype=float)
        return (conversion @ basis @ conversion.T).T.tolist()

    def mesh_data(self):
        # the mesh of a PKG part: {"vertices", "normals", "uvs", "submeshes": [(indices, texture)]}
        n = len(self.vertices)
        return {
            "vertices": self.vertices,
            "normals": self.normals if self.normals else [(0, 0, 1)] * n,
            "uvs": self.uvs if self.uvs else [(0, 0)] * n,
            "submeshes": [(s, self.properties.get("texture" + str(i), "NONE")) for i, s in enumerate(self.submeshes)],
        }


# the parts that are not surfaces of the PSDL
NOT_SURFACES = ("INST", "PTH", "PKG", "DECAL")


def is_surface(part):
    # the parts the PSDL writes in its rooms (RAIL: the tunnels, written even without faces)
    if part.type in NOT_SURFACES:
        return False
    return part.type == "RAIL" or (len(part.vertices) > 0 and part.num_triangles() > 0)


class Scene:
    def __init__(self, elements):
        self.parts = sorted((ScenePart(e) for e in elements), key=lambda p: p.name)
        self.blocks = self.get_blocks()

    def get_blocks(self):
        # the blocks (rooms) that have surfaces, in their order: the PSDL writes only those, so a block number of the
        # parts becomes the index of its block in this list (see block_index)
        if len(self.parts) == 0:
            return []
        n_blocks = max(p.block for p in self.parts)
        res = [[] for _ in range(n_blocks)]
        for p in self.parts:
            if is_surface(p) and p.block not in res[p.block - 1]:
                res[p.block - 1].append(p.block)
        return [b for b in res if len(b) > 0]

    def block_index(self, block):
        # the index of a block number in the PSDL (-1 if it isn't written)
        for i in range(len(self.blocks)):
            if block == self.blocks[i][0]:
                return i
        return -1

    def of_type(self, typ):
        return [p for p in self.parts if p.type == typ]
