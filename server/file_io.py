import struct


class BinaryFileHelper:
    def __init__(self, filepath, mode):
        self.file = open(filepath, mode)

    # Reading functions
    def read_byte(self):
        return self.file.read(1)[0]

    def read_bytes(self, num):
        return self.file.read(num)

    def read_uint32(self):
        return struct.unpack('<I', self.file.read(4))[0]

    def read_uint16(self):
        return struct.unpack('<H', self.file.read(2))[0]

    def read_float(self):
        return struct.unpack('<f', self.file.read(4))[0]

    def read_vec3(self):
        return struct.unpack('<f f f', self.file.read(4*3))

    def read_vec2(self):
        return struct.unpack('<f f', self.file.read(4*2))

    def read_quaternion(self):
        return struct.unpack('<f f f f', self.file.read(4*4))

    def read_string(self):
        length = self.read_byte()
        return str(self.file.read(length), 'utf-8')

    # Other
    def close(self):
        self.file.close()

    def tell(self):
        return self.file.tell()

    def seek(self, pos):
        self.file.seek(pos)
