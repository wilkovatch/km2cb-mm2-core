from utils import BinaryWriter


class BINExporter:
    def __init__(self, json_processor, verbose):
        self.json_processor = json_processor
        self.verbose = verbose

    def export_bin_file(self, filepath):
        print("Exporting BIN file...")
        elements = self.json_processor.get_objects()
        def write_element(writer, element):
            writer.write_byte(element.is_mesh)
            writer.write_string(element.name)
            writer.write_uint32(len(element.properties))
            for key in element.properties:
                writer.write_string(key)
                writer.write_string(element.properties[key])
            writer.write_uint32(len(element.vertices))
            for vert in element.vertices:
                writer.write_vec3(vert)
            writer.write_uint32(len(element.indices))
            if element.is_mesh:
                for j in range(len(element.indices)):
                    iJ = element.indices[j]
                    writer.write_uint32(len(iJ))
                    for i in range(len(iJ) - 1, -1, -1):
                        writer.write_uint16(iJ[i])
                for norm in element.normals:
                    writer.write_vec3(norm)
                for uv in element.uvs:
                    writer.write_vec2(uv)
            else:
                for i in range(len(element.indices) - 1, -1, -1):
                    writer.write_uint16(element.indices[i])
            mats = element.mat.split(',')
            writer.write_uint32(len(mats))
            for mat in mats:
                writer.write_string(mat)
            if element.translation == [0, 0, 0] and element.rotation == [0, 0, 0, 1] and element.scale == [1, 1, 1]:
                writer.write_byte(0)
            else:
                writer.write_byte(1)
                writer.write_vec3(element.translation)
                writer.write_vec3(element.scale)
                writer.write_float(-element.rotation[3])
                writer.write_float(element.rotation[0])
                writer.write_float(element.rotation[2])
                writer.write_float(element.rotation[1])
                
        writer = BinaryWriter(filepath)
        writer.write_raw(b'km2B')
        writer.write_string('MidtownMadness2')
        writer.write_uint32(len(elements))
        for element in elements:
            write_element(writer, element)
        writer.close()
        print("BIN file exported!")
