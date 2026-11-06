import os
from pathlib import Path


# the props types of parked car rows and single slots, exported by parked_car_export.py instead of as props
PARKED_CARS_TYPES = ('parkedCars', 'parkedCar')


def placed_props(line):
    # the props of a prop line of an element that have a model: the others are only places, for those who read them
    return [prop for prop in line['props'] if int(prop['meshId']) >= 0]

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
