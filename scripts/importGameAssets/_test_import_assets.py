"""Run with: python _test_import_assets.py. All archives and destinations are temporary synthetic data."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zlib

from _import_assets import DaveArchive, ImportFailure, import_assets


def archive_bytes(files):
    # Each tuple contains name, uncompressed bytes and whether to compress them. Deliberately pad both tables.
    index_size = ((len(files) * 16 + 0x7ff) // 0x800) * 0x800
    names = b''
    payloads = []
    name_offsets = []
    for name, data, compressed in files:
        name_offsets.append(len(names))
        names += name.encode('ascii') + b'\0'
        compressor = zlib.compressobj(wbits=-15)
        payloads.append(compressor.compress(data) + compressor.flush() if compressed else data)
    names_size = ((len(names) + 0x7ff) // 0x800) * 0x800
    offset = 0x800 + index_size + names_size
    index = b''
    for name_offset, (_, data, _), payload in zip(name_offsets, files, payloads):
        index += struct.pack('<4I', name_offset, offset, len(data), len(payload))
        offset += len(payload)
    header = struct.pack('<4sIII', b'DAVE', len(files), index_size, names_size)
    return header.ljust(0x800, b'\0') + index.ljust(index_size, b'\0') + names.ljust(names_size, b'\0') + b''.join(payloads)


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.game = self.root / 'game'
        self.game.mkdir()
        self.output = self.root / 'common'
        self.core = self.game / 'Mm2Core.Ar'
        self.tex = self.game / 'MM2TEX.AR'
        self.core.write_bytes(archive_bytes([
            ('Geometry\\Props\\Lamp.PKG', b'pkg' * 100, True),
            ('geometry/empty.pkg', b'', False),
            ('geometry/lamp.mtx', b'matrix', False),
            ('Tune/Banger/Lamp.dgBangerData', b'CG 0 1 0', False),
            ('City/materials.csv', b'texture,material\nlamp,metal', True),
            ('bound/lamp.bnd', b'ignored', False),
            ('city/sf.psdl', b'ignored', False),
        ]))
        self.tex.write_bytes(archive_bytes([
            ('Texture/Lamp.TEX', b'texture' * 100, True),
            ('texture/a.tga', b'tga', False),
            ('jpg/sf_maproam.jpg', b'ignored', False),
            ('texture/log.txt', b'ignored', False),
        ]))

    def assert_failure(self, key, action):
        with self.assertRaises(ImportFailure) as caught:
            action()
        self.assertEqual(caught.exception.key, key)
        return caught.exception

    def import_all(self, **kwargs):
        return import_assets(self.game, self.output, **kwargs)

    def read_first(self, data):
        self.core.write_bytes(data)
        with DaveArchive(self.core) as archive:
            return archive.read(archive.entries[0])

    def test_first_import_filters_and_lowercases_names(self):
        # Mods and loose files must not override the stock archives.
        (self.game / 'mod.ar').write_bytes(b'PK zip mod')
        (self.game / 'texture').mkdir()
        (self.game / 'texture/lamp.tex').write_bytes(b'override')
        result = self.import_all()
        self.assertEqual(result['imported'], 7)
        self.assertEqual(result['skipped'], 0)
        self.assertEqual(result['replaced'], 0)
        self.assertEqual(result['bytes_written'], sum(p.stat().st_size for p in self.output.rglob('*') if p.is_file()))
        self.assertEqual((self.output / 'geometry/props/lamp.pkg').read_bytes(), b'pkg' * 100)
        self.assertEqual((self.output / 'texture/lamp.tex').read_bytes(), b'texture' * 100)
        self.assertEqual((self.output / 'geometry/empty.pkg').read_bytes(), b'')
        self.assertEqual(len(list(p for p in self.output.rglob('*') if p.is_file())), 7)
        self.assertFalse((self.output / 'jpg').exists())
        self.assertFalse((self.output / 'bound').exists())

    def test_repeat_and_overwrite_preserve_other_files(self):
        self.import_all()
        texture = self.output / 'texture/lamp.tex'
        texture.write_bytes(b'custom')
        placeholder = self.output / 'texture/_put mm2 tex files here'
        placeholder.touch()
        other = self.output / 'texture/custom.png'
        other.write_bytes(b'keep')
        result = self.import_all()
        self.assertEqual(result, dict(imported=0, replaced=0, skipped=7, bytes_written=0))
        self.assertEqual(texture.read_bytes(), b'custom')
        result = self.import_all(overwrite=True)
        self.assertEqual(result['replaced'], 7)
        self.assertEqual(texture.read_bytes(), b'texture' * 100)
        self.assertTrue(placeholder.exists())
        self.assertEqual(other.read_bytes(), b'keep')

    def test_mixed_case_destination(self):
        folder = self.output / 'TeXtUrE'
        folder.mkdir(parents=True)
        existing = folder / 'LAMP.TEX'
        existing.write_bytes(b'keep')
        self.assertEqual(self.import_all()['skipped'], 1)
        self.assertEqual(existing.read_bytes(), b'keep')
        self.assertEqual(self.import_all(overwrite=True)['replaced'], 7)
        self.assertEqual(existing.read_bytes(), b'texture' * 100)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ['LAMP.TEX', 'a.tga'])
        self.assertEqual(len([p for p in self.output.iterdir() if p.name.lower() == 'texture']), 1)

    def test_missing_folder_and_archives(self):
        self.assert_failure('MM2_IMPORT_FOLDER_REQUIRED', lambda: import_assets('', self.output))
        self.assert_failure('MM2_IMPORT_FOLDER_MISSING', lambda: import_assets(self.root / 'absent', self.output))
        self.tex.unlink()
        self.assert_failure('MM2_IMPORT_ARCHIVE_MISSING', self.import_all)
        self.assertFalse(self.output.exists())

    def test_both_indexes_checked_before_writes(self):
        self.tex.write_bytes(b'DAVE')
        self.assert_failure('MM2_IMPORT_INDEX', self.import_all)
        self.assertFalse(self.output.exists())

    def test_padded_tables_stored_and_deflated(self):
        for compressed in (False, True):
            with self.subTest(compressed=compressed):
                self.assertEqual(self.read_first(archive_bytes([('geometry/a.pkg', b'test' * 100, compressed)])), b'test' * 100)

    def test_unsupported_signatures(self):
        for signature in (b'Dave', b'PK\x03\x04', b'xxxx'):
            with self.subTest(signature=signature):
                self.assert_failure('MM2_IMPORT_SIGNATURE', lambda: self.read_first(signature + b'\0' * 12))

    def test_bad_header_and_index_bounds(self):
        original = archive_bytes([('geometry/a.pkg', b'data', False)])
        for data in (b'', b'DAVE', original[:0x810]):
            self.assert_failure('MM2_IMPORT_INDEX', lambda: self.read_first(data))
        for offset, value in ((4, 0xffffffff), (8, 1), (12, 0xffffffff)):
            data = bytearray(original)
            struct.pack_into('<I', data, offset, value)
            self.assert_failure('MM2_IMPORT_INDEX', lambda: self.read_first(data))

    def test_invalid_names(self):
        original = archive_bytes([('geometry/a.pkg', b'data', False)])
        data = bytearray(original)
        struct.pack_into('<I', data, 0x800, 0xffffffff)
        self.assert_failure('MM2_IMPORT_NAME', lambda: self.read_first(data))
        data = bytearray(original)
        data[0x1000:0x1800] = b'a' * 0x800
        self.assert_failure('MM2_IMPORT_NAME', lambda: self.read_first(data))
        data[0x1000:0x1002] = b'\xff\0'
        self.assert_failure('MM2_IMPORT_NAME', lambda: self.read_first(data))

    def test_unsafe_paths(self):
        for name in ('/geometry/a.pkg', '../geometry/a.pkg', 'geometry/../a.pkg',
                     'C:\\geometry\\a.pkg', '\\\\server\\geometry\\a.pkg',
                     'geometry//a.pkg', 'geometry/./a.pkg', 'geometry/a.pkg:stream', 'geometry/a.pkg.', 'geometry/a?.pkg'):
            with self.subTest(name=name):
                self.assert_failure('MM2_IMPORT_UNSAFE_PATH', lambda: self.read_first(archive_bytes([(name, b'data', False)])))

    def test_invalid_payload_ranges(self):
        original = archive_bytes([('geometry/a.pkg', b'data', False)])
        for offset, value in ((0x804, 0), (0x804, len(original)), (0x80c, 0), (0x80c, 0xffffffff)):
            data = bytearray(original)
            struct.pack_into('<I', data, offset, value)
            self.assert_failure('MM2_IMPORT_PAYLOAD', lambda: self.read_first(data))
        self.assert_failure('MM2_IMPORT_PAYLOAD', lambda: self.read_first(original[:-1]))

    def test_corrupt_compression_and_size_mismatch(self):
        original = archive_bytes([('geometry/a.pkg', b'data' * 100, True)])
        for size in (1, 399, 401):
            data = bytearray(original)
            struct.pack_into('<I', data, 0x808, size)
            self.assert_failure('MM2_IMPORT_DECOMPRESSION', lambda: self.read_first(data))
        data = bytearray(original)
        data[0x1800:] = b'\xff' * (len(data) - 0x1800)
        self.assert_failure('MM2_IMPORT_DECOMPRESSION', lambda: self.read_first(data))
        data = bytearray(original[:-1])
        struct.pack_into('<I', data, 0x80c, len(data) - 0x1800)
        self.assert_failure('MM2_IMPORT_DECOMPRESSION', lambda: self.read_first(data))
        data = bytearray(original + b'junk')
        struct.pack_into('<I', data, 0x80c, len(data) - 0x1800)
        self.assert_failure('MM2_IMPORT_DECOMPRESSION', lambda: self.read_first(data))

    def test_duplicate_output_paths(self):
        self.core.write_bytes(archive_bytes([('geometry/A.pkg', b'a', False), ('geometry/a.pkg', b'b', False)]))
        self.assert_failure('MM2_IMPORT_DUPLICATE', self.import_all)
        self.assertFalse(self.output.exists())

    def test_empty_selection(self):
        self.tex.write_bytes(archive_bytes([('jpg/map.jpg', b'data', False)]))
        self.assert_failure('MM2_IMPORT_NO_ASSETS', self.import_all)
        self.assertFalse(self.output.exists())

    def test_file_directory_collision(self):
        self.output.mkdir()
        (self.output / 'geometry').touch()
        self.assert_failure('MM2_IMPORT_DESTINATION', self.import_all)

    def test_symlink_escape(self):
        self.output.mkdir()
        outside = self.root / 'outside'
        outside.mkdir()
        try:
            (self.output / 'geometry').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Creating symlinks is not permitted on this machine')
        self.assert_failure('MM2_IMPORT_DESTINATION', self.import_all)
        self.assertEqual(list(outside.iterdir()), [])

    def test_write_failure_cleans_temporary_file(self):
        with patch('_import_assets.os.replace', side_effect=PermissionError('synthetic failure')):
            error = self.assert_failure('MM2_IMPORT_IO', self.import_all)
        self.assertEqual(error.values['entry'], 'geometry/props/lamp.pkg')
        self.assertEqual(list(self.output.rglob('*.tmp')), [])
        self.assertFalse((self.output / 'geometry/props/lamp.pkg').exists())

    def test_partial_import_and_resume(self):
        original = self.core.read_bytes()
        data = bytearray(original)
        # Corrupt the last selected entry, leaving earlier completed files usable.
        offset = struct.unpack_from('<I', data, 0x800 + 4 * 16 + 4)[0]
        data[offset] = 0xff
        self.core.write_bytes(data)
        self.assert_failure('MM2_IMPORT_DECOMPRESSION', self.import_all)
        self.assertTrue((self.output / 'geometry/props/lamp.pkg').exists())
        self.assertFalse((self.output / 'city/materials.csv').exists())
        self.core.write_bytes(original)
        result = self.import_all()
        self.assertEqual(result['skipped'], 4)
        self.assertEqual(result['imported'], 3)

    def test_interrupted_run_and_progress(self):
        def stop(*args):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.import_all(progress=stop)
        self.assertTrue((self.output / 'geometry/props/lamp.pkg').exists())
        events = []
        result = self.import_all(progress=lambda *args: events.append(args))
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(events[-1][:2], (7, 7))
        self.assertLessEqual(len(events), 2)

    def adapter(self):
        client = types.SimpleNamespace(inputs=lambda: dict(gameFolder=str(self.game), overwriteExisting=False),
                                       progress=lambda *args: None, alert=lambda *args: None)
        spec = importlib.util.spec_from_file_location('import_assets_adapter', Path(__file__).with_name('main.py'))
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, citybuilder=client):
            spec.loader.exec_module(module)
        self.assertEqual(module.DESTINATION, Path(__file__).resolve().parents[4] / 'common' / 'MidtownMadness2')
        module.DESTINATION = self.output
        return module

    def test_adapter_progress_summary_and_defaults(self):
        module = self.adapter()
        progress, alerts = [], []
        module.cb.progress = lambda *args: progress.append(args)
        module.cb.alert = lambda *args: alerts.append(args)
        module.main()
        self.assertEqual(progress[0], (0, 'Checking the stock MM2 archives...'))
        self.assertEqual(progress[-1][0], 1)
        self.assertIn('7/7', progress[-1][1])
        summary, title = alerts[0]
        self.assertEqual(title, 'Import MM2 game assets')
        for expected in ('Imported: 7', 'Replaced: 0', 'Skipped: 0', 'Bytes written:', str(self.output), 'Save and reopen'):
            self.assertIn(expected, summary)
        metadata = json.loads(Path(__file__).with_name('script.json').read_text(encoding='utf-8'))
        self.assertFalse(metadata['transaction'])
        self.assertEqual([p['name'] for p in metadata['parameters']], ['gameFolder', 'overwriteExisting'])
        self.assertFalse(metadata['parameters'][1]['defaultValue'])

    def test_adapter_failure_keeps_actionable_error_on_one_line(self):
        module = self.adapter()
        self.tex.write_bytes(b'PK\x03\x04' + b'\0' * 12)
        with self.assertRaises(SystemExit) as caught:
            module.main()
        message = str(caught.exception)
        self.assertIn('MM2TEX.AR', message)
        self.assertIn('unsupported archive signature', message)
        self.assertIn('Completed files remain', message)
        self.assertNotIn('\n', message)  # ScriptRunner reports the last stderr line.
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
