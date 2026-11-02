from abc import ABC, abstractmethod


class SceneInput(ABC):
    @abstractmethod
    def init_progress_bar(self):
        pass

    @abstractmethod
    def set_progress_bar(self, value):
        pass

    @abstractmethod
    def end_progress_bar(self):
        pass

    @abstractmethod
    def get_object_list(self):
        pass

    @abstractmethod
    def get_object_name(self, obj):
        pass

    @abstractmethod
    def get_rotation(self, obj):
        pass

    @abstractmethod
    def get_property_container(self, obj):
        pass

    @abstractmethod
    def get_vertices_num(self, obj):
        pass

    @abstractmethod
    def get_vertex(self, obj, i):
        pass

    @abstractmethod
    def get_polygons_num(self, obj):
        pass

    @abstractmethod
    def get_polygon(self, obj, i):
        pass

    @abstractmethod
    def get_position(self, obj):
        pass

    @abstractmethod
    def get_scale(self, obj):
        pass

    @abstractmethod
    def create_composed_mesh(self):
        pass

    @abstractmethod
    def create_and_add_composed_mesh_from_object(self, obj, new_block):
        pass

    @abstractmethod
    def destroy_composed_mesh(self, mesh):
        pass

    @abstractmethod
    def remove_doubles(self, new_block, epsilon):
        pass

    # Mesh data of a PKG object (not abstract, only needed by the PKG writer):
    # {"vertices": [...], "normals": [...], "uvs": [...], "submeshes": [(indices, texture), ...]}
    # with the vertices already transformed
    def get_mesh_data(self, obj):
        raise NotImplementedError("get_mesh_data is not implemented by this scene input")
