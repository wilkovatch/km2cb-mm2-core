import os
import struct
from pathlib import Path


class BinaryWriter:
    def __init__(self, filepath):
        self.file = open(filepath, 'wb')

    def write_raw(self, value):
        self.file.write(value)

    def write_byte(self, value):
        self.file.write(bytes([value]))

    def write_string(self, string):
        length = len(string)
        self.write_byte(length)
        if length > 0:
            self.file.write(string.encode('ascii'))

    def write_uint32(self, value):
        byte_array = int(value).to_bytes(4, byteorder='little', signed=False)
        self.file.write(byte_array)

    def write_uint16(self, value):
        byte_array = int(value).to_bytes(2, byteorder='little', signed=False)
        self.file.write(byte_array)

    def write_float(self, value):
        float_value = float(value)
        self.file.write(struct.pack('<f', float_value))

    def write_vec3(self, value):
        self.write_float(value[0])
        self.write_float(value[2])
        self.write_float(value[1])

    def write_vec2(self, value):
        self.write_float(value[0])
        self.write_float(value[1])

    def close(self):
        self.file.close()

# Functions to get a value from a dictionary without throwing an error if the state or the key is missing
def state_val(state, key, default = None):
    if state is None or type(state) is not dict:
        return default
    elif key in state:
        return state[key]
    else:
        return default

def state_bool(state, key):
    return state_val(state, key, False)

def state_int(state, key):
    return state_val(state, key, 0)

def state_vector(state, key):
    return state_val(state, key, {"x": 0, "y": 0, "z": 0})

def state_vector_scale(state, key):
    return state_val(state, key, {"x": 1, "y": 1, "z": 1})

def clean_city_path(filename):
    return str(Path(str(Path(filename).with_suffix(''))).with_suffix(''))

def create_folder_if_not_exists(foldername):
    if not os.path.exists(foldername): os.makedirs(foldername)
