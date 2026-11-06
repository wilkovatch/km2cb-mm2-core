# The arguments of export.py: the Files/python folder of the program, the input JSON, the chosen output file, then a
# 0/1 value for each flag of settings.json, in its order (the program passes them so, see the Core Python Integration
# page of the wiki)

import json
import os

SETTINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.json')


def flag_ids():
    with open(SETTINGS, encoding='utf-8') as f:
        return [flag['id'] for flag in json.load(f)['flags']]


class ExportOptions:
    def __init__(self, python_dir, input_json, output, flags):
        self.python_dir = python_dir
        self.input_json = input_json
        self.output = output
        self.flags = flags

    @staticmethod
    def from_argv(argv):
        ids = flag_ids()
        values = argv[4:]
        if len(argv) < 4 or len(values) != len(ids):
            raise Exception("Wrong number of arguments: expected the Files/python folder, the input JSON, the output file and "
                            + str(len(ids)) + " flags (" + ", ".join(ids) + "), got " + str(len(argv) - 1) + " arguments")
        return ExportOptions(argv[1], argv[2], argv[3], {i: int(v) > 0 for i, v in zip(ids, values)})

    def __getitem__(self, flag_id):
        return self.flags[flag_id]
