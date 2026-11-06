"""Repeat exports through the entry point and real file writers, with small synthetic parts and no game assets."""
import contextlib
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

CORE = Path(__file__).resolve().parents[3]
EXPORTER = CORE / 'exporters/psdl'
sys.path[:0] = [str(EXPORTER), str(CORE.parents[1] / 'python')]

import ExportReport
from psdl_parts import ExportedCityElement
from options import flag_ids
from traffic.model import BaiNetwork
from _test_parked_cars import single
from _test_boats import boat, LOOP
from _test_bridges import bridge
from _test_prop_placers import read_paths


def part(name, vertices=(), indices=(), **properties):
    element = ExportedCityElement()
    element.name = name
    element.vertices = list(vertices)
    element.indices = list(indices)
    element.properties = properties
    element.mat = 'ground'
    return element


def processor(data, verbose):
    # Isolate geometry extraction, while exercising every actual writer and export flag.
    vertices = [(-10, 0, -10), (-10, 0, 10), (10, 0, 10), (10, 0, -10)]
    ground = part('1_BLOCK', vertices, [0, 1, 2, 0, 2, 3])
    pkg = part('1_PKG', vertices, [[0, 1, 2, 0, 2, 3]], pkg_name='mesh0', lod_name='VL')
    pkg.is_mesh = True
    pkg.normals = [(0, 1, 0)] * 4
    pkg.uvs = [(0, 0), (0, 1), (1, 1), (1, 0)]
    parts = [ground, pkg, part('1_INST', object='tree'),
             part('0_PTH', [(0, 0, 0), (0, 0, 12)], object='tree', flags='2', spacing='24'),
             part('0_PTH', [(1, 0, 0), (1, 0, 12)], object='tree', flags='2', spacing='24', race='A'),
             part('0_DECAL', [(-1, 0, 0), (1, 0, 0), (-1, 0, 5), (1, 0, 5)], texture='decal', strip_pairs='1')]
    mesh = dict(vertices=vertices, submeshes=[dict(indices=ground.indices, materialId=-1)])
    data.setdefault('terrainPatches', [dict(data=dict(mesh=mesh, fields=dict(state={})))])
    return SimpleNamespace(data=data, get_objects=lambda: parts, prop_rules=[], network=BaiNetwork(),
                           exported_roads={}, traffic=SimpleNamespace(chains=[]))


def city():
    opponent = dict(carModel=dict(meshPath='geometry/vpbug.pkg'), waypoints=[dict(waypoint=dict(localPosition=dict(x=1, y=0, z=2)))])
    race = dict(_elementContainerId='A', opponents=dict(opponents=[opponent]), checkpoints=[])
    elements = [single(), single(owner='A'), boat('Boat', 0, LOOP), boat('Ferry', 5, LOOP), bridge(), bridge(1, _propertyContainerId='A'),
                dict(type='train', data=dict(name='Train'), points=dict(spline=[dict(id=i, position=p) for i, p in enumerate(LOOP)]))]
    for i, element in enumerate(elements):
        element['id'] = i
        element['data'].setdefault('fields', {}).setdefault('state', {})
    return dict(cityProperties=dict(cityName='Test', circuitRaces=[race]), customElements=elements)


class ExportOverwrite(unittest.TestCase):
    def run_export(self, folder, data=None, expected_exit=0, **flags):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        source = folder / 'input.json'
        source.write_text(json.dumps(data if data is not None else city()), encoding='utf-8')
        # No common assets: the modules are already on sys.path; this path locates an empty common folder.
        argv = [str(EXPORTER / 'export.py'), str(folder / 'modules'), str(source), str(folder / 'test.psdl')]
        values = dict.fromkeys(flag_ids(), True)
        values.update(psdl_splitNonCoplanarRoads=False, bai_accurateCulling=False, psdl_capMaterials=False, verbose=False, packAr=False)
        values.update(flags)
        argv.extend(str(int(value)) for value in values.values())
        output = io.StringIO()
        exit_code = 0
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(sys, 'argv', argv))
            stack.enter_context(patch('json_processor.JsonProcessor', processor))
            stack.enter_context(patch.object(ExportReport, '_counts', dict.fromkeys(ExportReport.LEVELS, 0)))
            stack.enter_context(patch.object(ExportReport, '_file', None))
            stack.enter_context(contextlib.redirect_stdout(output))
            stack.enter_context(contextlib.redirect_stderr(output))
            try:
                runpy.run_path(str(EXPORTER / 'export.py'), run_name='__main__')
            except SystemExit as exc:
                exit_code = exc.code
            self.assertEqual(expected_exit, exit_code, output.getvalue())
            self.assertEqual(bool(expected_exit), bool(ExportReport.has_errors()), output.getvalue())

    def snapshot(self, folder):
        return {p.relative_to(folder).as_posix(): p.read_bytes() for p in Path(folder).rglob('*')
                if p.is_file() and p.name != 'input.json'}

    def test_every_loose_output_overwrites_longer_old_files(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_export(directory)
            expected = self.snapshot(directory)
            # Assert coverage so an accidentally skipped writer cannot make this test pass.
            required = {'city/test.psdl', 'city/test.inst', 'city/test.bai', 'city/test.aimap',
                        'city/test/props.pathset', 'city/test/decals.pathset', 'city/test/propdefs.csv', 'city/test/proprules.csv',
                        'tune/test.cinfo', 'tune/test.mmHudMap', 'geometry/test_mesh0.pkg', 'geometry/hudmap_test.pkg',
                        'bound/test_mesh0_BOUND.bnd', 'bound/test_mesh0_BOUND.bbnd', 'bound/test_mesh0_BOUND.ter',
                        'texture/test_hudmap0.tex', 'texture/test_hudmap0_ni.tex',
                        'jpg/test_maproam.jpg', 'jpg/test_mapcircuit0.jpg', 'test_hudmap_preview.png', 'test_hudmap_labels_preview.png',
                        'race/test/circuit0.pathset', 'race/test/circuit0.aimap', 'race/test/circuit0.aimap_p',
                        'race/test/circuit0-a-0.opp', 'race/test/circuit0-p-0.opp', 'race/test/circuit0waypoints.csv',
                        'race/test/mmblitzdata.csv', 'race/test/mmcircuitdata.csv', 'race/test/mmracedata.csv',
                        'race/test/roam.aimap', 'race/test/roam.aimap_p', 'race/test/test_parkedcar.pathset',
                        'race/test/test_parkedcar_circuit0.pathset', 'race/test/test_train.pathset',
                        'race/test/test_sailboat.pathset', 'race/test/test_ferry.pathset',
                        'race/test/test_bridge.pathset', 'race/test/test_bridge_circuit0.pathset'}
            self.assertTrue(required <= expected.keys(), required - expected.keys())
            for name, payload in expected.items():
                if not Path(name).name.startswith('.km2-'):
                    (Path(directory) / name).write_bytes(b'old output' + payload + b'stale trailing bytes' * 100)
            self.run_export(directory)
            actual = self.snapshot(directory)
            self.assertEqual(expected.keys(), actual.keys())
            for name in expected:
                with self.subTest(file=name):
                    self.assertEqual(expected[name], actual[name])

    def test_pathset_only_refreshes_city_routes_without_city_properties(self):
        data = city()
        del data['cityProperties']
        data['customElements'] = [e for e in data['customElements'] if not e['data']['fields']['state'].get('_propertyContainerId')]
        flags = dict(propRules=False, psdl=False, inst=False, bai=False, cinfo_aimap=False, hudmap=False, pkgs=False)
        with tempfile.TemporaryDirectory() as directory:
            self.run_export(directory, data, **flags)
            path = Path(directory) / 'race/test/test_parkedcar.pathset'
            self.assertEqual(read_paths(path)[0][3][0], (-3, 7, 11))
            data['customElements'][0]['data']['propLines'][0]['props'][0]['position'] = [30, 7, 11]
            self.run_export(directory, data, **flags)
            self.assertEqual(read_paths(path)[0][3][0], (-30, 7, 11))
            for kind in ('train', 'sailboat', 'ferry', 'bridge'):
                self.assertTrue(path.with_name('test_' + kind + '.pathset').exists())
            data['customElements'] = []
            self.run_export(directory, data, **flags)
            for kind in ('parkedcar', 'train', 'sailboat', 'ferry', 'bridge'):
                self.assertFalse(path.with_name('test_' + kind + '.pathset').exists())

    def test_cinfo_only_preserves_disabled_pathset_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_export(directory)
            before = {k: v for k, v in self.snapshot(directory).items() if k.endswith('.pathset')}
            data = city()
            data['customElements'] = []
            self.run_export(directory, data, pathset=False)
            self.assertEqual(before, {k: v for k, v in self.snapshot(directory).items() if k.endswith('.pathset')})

    def test_failed_train_writer_does_not_skip_boats_and_parked_cars(self):
        with tempfile.TemporaryDirectory() as directory, patch('train_export.export_trains', side_effect=ValueError('invalid train')):
            self.run_export(directory, cinfo_aimap=False, expected_exit=1)
            folder = Path(directory) / 'race/test'
            for kind in ('parkedcar', 'sailboat', 'ferry', 'bridge'):
                self.assertTrue(read_paths(folder / ('test_' + kind + '.pathset')))

    def test_archive_and_preview_outputs_replace_previous_export(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_export(directory, packAr=True)
            archive = Path(directory) / 'test.ar'
            def entries():
                with zipfile.ZipFile(archive) as stream:
                    return {name: stream.read(name) for name in stream.namelist()}
            expected = entries()
            self.assertIn('race/test/test_parkedcar.pathset', expected)
            with zipfile.ZipFile(archive, 'a') as stream:
                stream.writestr('obsolete.txt', 'old export')
            previews = {p: p.read_bytes() for p in Path(directory).glob('*.png')}
            self.assertEqual(len(previews), 2)
            for path in previews:
                path.write_bytes(b'old preview' * 1000)
            self.run_export(directory, packAr=True)
            self.assertEqual(expected, entries())
            for path, payload in previews.items():
                self.assertEqual(payload, path.read_bytes())


if __name__ == '__main__':
    unittest.main()
