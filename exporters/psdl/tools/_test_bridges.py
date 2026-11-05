"""Small native bridge export regressions; fixtures contain no original game assets."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE/'exporters/psdl'), str(CORE.parents[1]/'python')]
from bridge_export import get_bridges, export_bridges, STOCK_MODELS, PREFIXES, MANIFEST, TUNING_MANIFEST
from prop_placers import export_prop_placer
from _test_boats import read_pathset


def bridge(index=0, **state):
    return dict(id=index, type='bridge', data=dict(name='Bridge ' + str(index), fields=dict(state=state),
                propLines=[dict(name='towerStart', props=[dict(meshId=0)])]),
                points=dict(start=dict(position=[5, 8, 10]), finish=dict(position=[5, 8, 70])))


def stock(index):
    return 'geometry/' + STOCK_MODELS[index % 3] + '.pkg'


def write_pkg(path, vertices):
    # a PKG with a single part, with only the positions
    path.parent.mkdir(parents=True, exist_ok=True)
    geometry = struct.pack('<IIIII', 1, len(vertices), 0, 1, 0) + struct.pack('<HHI', 1, 0, 0) + struct.pack('<II', 3, len(vertices))
    for v in vertices:
        geometry += struct.pack('<fff', *v)
    geometry += struct.pack('<I', 0)
    path.write_bytes(b'PKG3FILE' + bytes([2]) + b'H\0' + struct.pack('<I', len(geometry)) + geometry)


class Bridges(unittest.TestCase):
    def test_native_names_layout_mirroring_and_preview_independence(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            elements = [bridge(i, mesh=stock(i), behavior=i, paired=i != 2) for i in range(4)]
            data = dict(customElements=elements)
            export_bridges(data, directory, 'x')
            path = folder/'x_bridge.pathset'
            before = path.read_bytes()
            paths = read_pathset(path)
            self.assertEqual([p['name'] for p in paths], [PREFIXES[i] + STOCK_MODELS[i % 3] for i in range(4)])
            self.assertEqual([len(p['points']) for p in paths], [3, 3, 2, 3])
            self.assertEqual(paths[0]['points'], [(0, -5, 8, 10), (0, -5, 8, 40), (0, -5, 8, 70)])
            self.assertTrue(all((p['type'], p['spacing'], p['extra'], p['pad']) == (2, 20, 0, 0) for p in paths))
            for e in elements:
                e['data']['fields']['state']['preview'] = 2
                e['data']['propLines'] = []
            export_bridges(data, directory, 'x')
            self.assertEqual(before, path.read_bytes())

    def test_race_replacements_keep_other_city_bridges_and_support_all_races(self):
        data = dict(customElements=[bridge(), bridge(1, mesh=stock(1)), bridge(2, _propertyContainerId='A', behavior=3,
                    replaces=dict(kind='customElement', id=0)), bridge(3, _propertyContainerId='B'), bridge(4, _propertyContainerId='C')],
                    cityProperties=dict(circuitRaces=[dict(_elementContainerId='A')], blitzRaces=[dict(_elementContainerId='B')],
                                        checkpointRaces=[dict(_elementContainerId='C')]))
        original = copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            export_bridges(data, directory, 'x')
            self.assertEqual([p['name'] for p in read_pathset(folder/'x_bridge_circuit0.pathset')],
                             ['open:giz_bridge01_l', 'time:giz_waterloo_l'])
            for race in ('blitz0', 'race0'):
                self.assertEqual(len(read_pathset(folder/('x_bridge_' + race + '.pathset'))), 3)
            self.assertEqual(len(read_pathset(folder/'x_bridge.pathset')), 2)
            self.assertEqual(data, original)

    def test_stale_cleanup_and_repeat_export_preserve_unowned_files(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            unrelated = folder/'x_bridge_race9.pathset'
            unrelated.write_bytes(b'hand-authored')
            data = dict(customElements=[bridge(), bridge(1, _propertyContainerId='A')],
                        cityProperties=dict(circuitRaces=[dict(_elementContainerId='A')]))
            export_bridges(data, directory, 'x')
            main = folder/'x_bridge.pathset'
            main.write_bytes(main.read_bytes() + b'obsolete trailing bytes')
            data['customElements'] = [bridge(paired=False)]
            export_bridges(data, directory, 'x')
            self.assertEqual(len(read_pathset(main)[0]['points']), 2)
            self.assertFalse((folder/'x_bridge_circuit0.pathset').exists())
            self.assertEqual(json.loads((folder/MANIFEST).read_text()), [])
            export_bridges({}, directory, 'x')
            self.assertFalse(main.exists())
            self.assertEqual(unrelated.read_bytes(), b'hand-authored')

    def test_invalid_points_modes_and_replacements_fail_with_element_diagnostics(self):
        bad = [bridge(0, mesh='geometry/x.obj'), bridge(1, behavior=-1), bridge(2, paired=1),
               bridge(3, replaces=dict(kind='customElement', id=0)),
               bridge(4, _propertyContainerId='A', replaces=dict(kind='customElement', id=99))]
        bad.append(bridge(5))
        bad[-1]['points']['finish']['position'] = [5, 40, 10]
        bad.append(bridge(6))
        bad[-1]['points']['start']['position'][0] = float('nan')
        with patch('bridge_export.report.error') as error:
            self.assertEqual(get_bridges(dict(customElements=bad, cityProperties=dict(circuitRaces=[dict(_elementContainerId='A')]))), [])
            self.assertEqual(error.call_count, len(bad))
            self.assertTrue(all(c.kwargs['kind'] == 'customElement' for c in error.call_args_list))

    def test_an_element_without_a_model_uses_the_default(self):
        self.assertEqual(get_bridges(dict(customElements=[bridge()]))[0]['route'][0], 'time:giz_bridge01_l')

    def test_stock_models_need_no_assets_nor_tuning(self):
        with tempfile.TemporaryDirectory() as directory, patch('bridge_export.report.error') as error:
            race = Path(directory)/'race'/'x'
            race.mkdir(parents=True)
            export_bridges(dict(customElements=[bridge(i, mesh=stock(i)) for i in range(3)]), race, 'x')
            error.assert_not_called()
            self.assertEqual(len(read_pathset(race/'x_bridge.pathset')), 3)
            self.assertFalse((Path(directory)/'tune').exists())

    def custom_export(self, directory, write_files):
        root = Path(directory)
        race, city, common = root/'out'/'race'/'x', root/'city', root/'common'
        race.mkdir(parents=True)
        write_files(city, common)
        data = dict(customElements=[bridge(mesh='geometry/My_Leaf.pkg')], cityFolder=str(city))
        export_bridges(data, race, 'x', str(common))
        return race, root/'out'/'tune'/'banger'

    def test_a_custom_model_gets_banger_data_from_its_size(self):
        # gizBridge::UpdateMatrix crashes without it: the size decides the hinge, in the same order as the stock files
        with tempfile.TemporaryDirectory() as directory, patch('bridge_export.report.error') as error:
            race, tune = self.custom_export(directory, lambda city, common: write_pkg(city/'geometry'/'my_leaf.pkg', [(-4, -1, -6), (4, 1, 6)]))
            error.assert_not_called()
            self.assertEqual(read_pathset(race/'x_bridge.pathset')[0]['name'], 'time:My_Leaf')
            text = (tune/'My_Leaf.dgBangerData').read_text()
            self.assertTrue(text.startswith('type: a\ndgBangerData {\n'))
            self.assertIn('Size 8.000000\t2.000000\t12.000000\n', text)
            self.assertIn('CG 0.000000\t0.000000\t0.000000\n', text)
            self.assertIn('Mass 153600.000000\n', text)
            # a later export without the bridge removes it, as it's owned by the exporter
            export_bridges({}, race, 'x')
            self.assertFalse((tune/'My_Leaf.dgBangerData').exists())
            self.assertEqual(json.loads((tune/TUNING_MANIFEST).read_text()), [])

    def test_banger_data_of_the_city_is_exported_and_of_the_game_is_not_needed(self):
        def city_file(city, common):
            write_pkg(city/'geometry'/'my_leaf.pkg', [(0, 0, 0), (1, 1, 1)])
            (city/'tune'/'banger').mkdir(parents=True)
            (city/'tune'/'banger'/'my_leaf.dgbangerdata').write_text('authored')
        with tempfile.TemporaryDirectory() as directory:
            _, tune = self.custom_export(directory, city_file)
            self.assertEqual((tune/'My_Leaf.dgBangerData').read_text(), 'authored')

        def game_file(city, common):
            (common/'tune'/'banger').mkdir(parents=True)
            (common/'tune'/'banger'/'My_Leaf.dgBangerData').write_text('stock')
        with tempfile.TemporaryDirectory() as directory, patch('bridge_export.report.error') as error:
            race, tune = self.custom_export(directory, game_file)
            error.assert_not_called()
            self.assertEqual(len(read_pathset(race/'x_bridge.pathset')), 1)
            self.assertFalse(tune.exists())

    def test_an_existing_file_is_not_overwritten_by_the_generated_banger_data(self):
        with tempfile.TemporaryDirectory() as directory, patch('bridge_export.report.warning') as warning:
            tune = Path(directory)/'out'/'tune'/'banger'
            tune.mkdir(parents=True)
            (tune/'My_Leaf.dgBangerData').write_text('hand-authored')
            self.custom_export(directory, lambda city, common: write_pkg(city/'geometry'/'My_Leaf.pkg', [(0, 0, 0), (1, 1, 1)]))
            self.assertEqual((tune/'My_Leaf.dgBangerData').read_text(), 'hand-authored')
            warning.assert_called_once()

    def test_a_model_that_can_crash_the_game_is_not_exported(self):
        # no PKG (so no size), an unreadable PKG, a name the game splits or that doesn't fit in the path name
        def unreadable(city, common):
            (city/'geometry').mkdir(parents=True)
            (city/'geometry'/'My_Leaf.pkg').write_bytes(b'nope')
        for files in (lambda city, common: None, unreadable):
            with tempfile.TemporaryDirectory() as directory, patch('bridge_export.report.error') as error:
                race, tune = self.custom_export(directory, files)
                error.assert_called_once()
                self.assertFalse((race/'x_bridge.pathset').exists())
                self.assertFalse((tune/'My_Leaf.dgBangerData').exists())
        with patch('bridge_export.report.error') as error:
            bad = [bridge(0, mesh='geometry/a:b.pkg'), bridge(1, mesh='geometry/a@b.pkg'), bridge(2, mesh='geometry/' + 'x' * 28 + '.pkg'), bridge(3, mesh='geometry/\u00e8.pkg')]
            self.assertEqual(get_bridges(dict(customElements=bad)), [])
            self.assertEqual(error.call_count, len(bad))
        self.assertEqual(len(get_bridges(dict(customElements=[bridge(mesh='geometry/' + 'x' * 27 + '.pkg')]))), 1)

    def test_multiple_replacements_of_one_bridge_fail(self):
        data = dict(customElements=[bridge(), *[bridge(i, _propertyContainerId='A', replaces=dict(kind='customElement', id=0)) for i in (1, 2)]],
                    cityProperties=dict(circuitRaces=[dict(_elementContainerId='A')]))
        with tempfile.TemporaryDirectory() as directory, patch('bridge_export.report.error') as error:
            export_bridges(data, directory, 'x')
            error.assert_called_once()
            self.assertFalse((Path(directory)/'x_bridge_circuit0.pathset').exists())

    def test_preview_props_never_become_static_props_or_inst(self):
        parts = []
        export_prop_placer(None, bridge(), parts)
        self.assertEqual(parts, [])

    def test_path_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory, patch('bridge_export.report.error') as error:
            export_bridges(dict(customElements=[bridge(i) for i in range(193)]), directory, 'x')
            error.assert_called_once()
            self.assertEqual(len(read_pathset(Path(directory)/'x_bridge.pathset')), 192)


if __name__ == '__main__':
    unittest.main()
