"""Synthetic checks for the INST modifiers: the version-7 migration, the values the exporter gives and the written records."""
import copy
import importlib.util
import pathlib
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

CORE = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE / 'exporters/psdl'), str(CORE.parents[1] / 'python')]

from writers.file_io import BinaryFileHelper
from writers.inst_writer import INSTWriter
import json_processor

spec = importlib.util.spec_from_file_location('inst_modifiers_migration', CORE / 'migrations/7.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

# every value of the stock sf.inst and london.inst, without their data
STOCK_VALUES = [*range(10), 12, 0x0100, 0x2000]


def inst_mesh(**settings):
    return dict(type='instMesh', name='Mesh 1', settings=dict(type='instMesh', **settings))


def exported(**settings):
    with patch.object(json_processor.report, 'warning') as warning:
        value = json_processor.get_inst_modifiers(inst_mesh(), settings)
    return value, [call.args[0] for call in warning.call_args_list]


def migrated(*meshes):
    return migration.migrate_city(dict(meshes=list(meshes)))['meshes']


class Migration(unittest.TestCase):
    def test_values(self):
        table = {0: (False, False, False, False, 0), 3: (False, False, False, False, 3),
                 256: (True, False, False, False, 0), 258: (True, False, False, False, 2),
                 0x0200: (False, True, False, False, 0), 0x0500: (True, False, True, False, 0),
                 0x2000: (False, False, False, True, 0), 0x21ff: (True, False, False, True, 255)}
        for raw, expected in table.items():
            settings = migrated(dict(settings=dict(type='instMesh', instModifiers=raw)))[0]['settings']
            self.assertNotIn('instModifiers', settings)
            names = ('instLandmark', 'instBanger', 'instSimpleCollision', 'instMultiroom', 'instPaintJob')
            self.assertEqual(tuple(settings[name] for name in names), expected, raw)

    def test_missing_value_was_exported_as_landmark(self):
        settings = migrated(dict(settings=dict(type='instMesh')))[0]['settings']
        self.assertTrue(settings['instLandmark'])
        self.assertEqual(settings['instPaintJob'], 0)

    def test_other_meshes_and_the_source_are_not_changed(self):
        source = dict(meshes=[dict(settings=dict(type='individualProp')), dict(settings=dict(_parameterName='a')), dict()])
        before = copy.deepcopy(source)
        self.assertEqual(migration.migrate_city(source), before)
        with_value = dict(meshes=[dict(settings=dict(type='instMesh', instModifiers=256))])
        before = copy.deepcopy(with_value)
        migration.migrate_city(with_value)
        self.assertEqual(with_value, before)

    def test_bits_the_game_does_not_read_are_removed(self):
        settings = migrated(dict(settings=dict(type='instMesh', instModifiers=0x0900)))[0]['settings']
        self.assertEqual(exported(**settings)[0], 0x0100)

    def test_stock_values_round_trip(self):
        for raw in STOCK_VALUES:
            settings = migrated(dict(settings=dict(type='instMesh', instModifiers=raw)))[0]['settings']
            value, warnings = exported(**settings)
            self.assertEqual(value, raw)
            self.assertEqual(warnings, [])


class Exporter(unittest.TestCase):
    def test_bits(self):
        self.assertEqual(exported()[0], 0)
        self.assertEqual(exported(instLandmark=True)[0], 0x0100)
        self.assertEqual(exported(instBanger=True)[0], 0x0200)
        self.assertEqual(exported(instLandmark=True, instSimpleCollision=True)[0], 0x0500)
        self.assertEqual(exported(instMultiroom=True, instPaintJob=7)[0], 0x2007)

    def test_parametric_objects_are_landmarks(self):
        self.assertEqual(json_processor.get_inst_modifiers(dict(type=None, name='a'), {'_parameterName': 'a'}), 0x0100)

    def test_warnings(self):
        for settings in (dict(instSimpleCollision=True), dict(instBanger=True, instLandmark=True),
                         dict(instBanger=True, instSimpleCollision=True), dict(instMultiroom=True, instLandmark=True)):
            self.assertEqual(len(exported(**settings)[1]), 1, settings)
        for settings in (dict(instLandmark=True), dict(instLandmark=True, instSimpleCollision=True), dict(instBanger=True),
                         dict(instMultiroom=True), dict(instPaintJob=255)):
            self.assertEqual(exported(**settings)[1], [], settings)

    def test_paint_job_is_kept_in_its_byte(self):
        for paint_job, expected in ((256, 255), (-1, 0)):
            value, warnings = exported(instPaintJob=paint_job, instLandmark=True)
            self.assertEqual(value, 0x0100 | expected)
            self.assertEqual(len(warnings), 1)


class Writer(unittest.TestCase):
    def test_records(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / 'test.inst'
            writer = INSTWriter.__new__(INSTWriter)
            writer.file = BinaryFileHelper(str(path), 'wb')
            writer.object_names = set()
            writer.scene = SimpleNamespace(block_index=lambda block: 0)
            writer.process_pkg_group(SimpleNamespace(pivot=(0, 0, 0), block=0, stem='group'))
            writer.export_elem([0, 0, 0], 1, 1, 1, (0, 0, 0), 0, 'mesh', 0x2007)
            writer.file.close()
            data = path.read_bytes()
        self.assertEqual(struct.unpack_from('<HH', data, 0), (1, 0x0100))
        second = 5 + len('group') + 1 + 8 + 12
        self.assertEqual(struct.unpack_from('<HH', data, second), (1, 0x2007))


if __name__ == '__main__':
    unittest.main()
