import struct


class BinaryFileHelper:
    def __init__(self, filepath, mode):
        self.file = open(filepath, mode)

    # Reading functions
    def read_byte(self):
        return self.file.read(1)[0]

    def read_uint32(self):
        return struct.unpack('<I', self.file.read(4))[0]

    def read_uint16(self):
        return struct.unpack('<H', self.file.read(2))[0]

    def read_float(self):
        return struct.unpack('<f', self.file.read(4))[0]

    def read_vec2(self):
        return struct.unpack('<f f', self.file.read(4*2))

    def read_vec3(self):
        return struct.unpack('<f f f', self.file.read(4*3))

    def read_quaternion(self):
        return struct.unpack('<f f f f', self.file.read(4*4))

    def read_string(self):
        length = self.read_byte()
        return str(self.file.read(length), 'utf-8')

    # Writing functions
    def write_byte(self, value):
        self.file.write(bytes([value]))

    def write_raw_string(self, string):
        self.file.write(string.encode('ascii'))

    def write_zero_terminated_string(self, string):
        self.file.write(string.encode('ascii'))
        self.write_byte(0)

    def write_string(self, string):
        length = len(string)
        if length > 0:
            self.write_byte(length+1)
            self.file.write(string.encode('ascii'))
        self.write_byte(0)

    def write_string32(self, string):
        length = len(string)
        if length > 32:
            raise Exception("String32 too long (max is 32 chars): " + string)
        else:
            self.file.write(string.encode('ascii'))
            for i in range(32-length):
                self.write_byte(0)

    def write_uint32(self, value):
        byte_array = int(value).to_bytes(4, byteorder='little', signed=False)
        self.file.write(byte_array)

    def write_int32(self, value):
        byte_array = int(value).to_bytes(4, byteorder='little', signed=True)
        self.file.write(byte_array)

    def write_uint16(self, value):
        byte_array = int(value).to_bytes(2, byteorder='little', signed=False)
        self.file.write(byte_array)

    def write_int16(self, value):
        byte_array = int(value).to_bytes(2, byteorder='little', signed=True)
        self.file.write(byte_array)

    def write_float(self, value):
        float_value = float(value)
        self.file.write(struct.pack('<f', float_value))

    def write_vec3(self, value):
        self.write_float(-(value[0]))
        self.write_float(value[2])
        self.write_float(value[1])

    def close(self):
        self.file.close()

    def tell(self):
        return self.file.tell()

    def seek(self, pos):
        self.file.seek(pos)
