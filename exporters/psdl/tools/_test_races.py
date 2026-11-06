"""Short synthetic checks for race migration, OPP parity and race-scoped PATHSET output."""
import contextlib
import copy
import gzip
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import zipfile
from unittest.mock import patch

CORE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(CORE / 'exporters/psdl'))
sys.path.insert(0, str(CORE.parents[1] / 'python'))
from MigrationHelper import MigrationHelper
from _test_prop_placers import read_paths, line
from prop_placers import export_prop_placer
from scene import Scene
from writers.pathset_writer import PATHSETWriter
from race_elements import opponents, write_props, validate_ownership
from output_layout import OutputLayout
from cinfo_aimap_export import CinfoAimapExporter
from ar_packer import ArPacker

spec = importlib.util.spec_from_file_location('race_migration', CORE / 'migrations/5.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def opponent():
    return dict(carModel=dict(meshPath='geometry/vpbug.pkg', localPosition=dict(x=1.0, y=2.0, z=3.0), localRotation=dict(x=0.0, y=0.0, z=0.0)),
                waypoints=[dict(waypoint=dict(localPosition=dict(x=4.0, y=5.0, z=6.0))), dict(waypoint=dict(localPosition=dict(x=7.0, y=8.0, z=9.0)))],
                speedMultiplier=1.25, avoidProps=True, cautionInCorners=45.0, extraField='keep')


def exported(saved):
    data = copy.deepcopy(saved)
    points = {p['id']: list(p['position'].values()) for p in data['terrainPoints']}
    data['customElements'] = [dict(id=e['id'], type=e['state']['type'], data=dict(name=e['name'], fields=dict(state=e['state'])),
                                   points=dict(spline=[dict(id=i, position=points[i]) for i in e['points']['spline']]))
                             for e in data.get('customElements') or data.get('lowLevelElements') or []]
    return data


class Races(unittest.TestCase):
    def test_migration_and_opponent_export_parity(self):
        amateur, professional = opponent(), opponent()
        professional['speedMultiplier'] = 1.5
        race = dict(name='Synthetic race', checkpoints=[], opponents=dict(opponents=[amateur]), opponents_professional=dict(opponents=[professional]))
        source = dict(cityProperties=dict(circuitRaces=[race], checkpointRaces=[dict(name='Empty')], unrelated=42),
                      customElements=[], terrainPoints=[dict(id=9, position=dict(x=0.0,y=0.0,z=0.0))])
        untouched = copy.deepcopy(source)
        saved = migration.migrate_city(source)
        self.assertEqual(source, untouched)
        self.assertEqual(saved['cityProperties']['unrelated'], 42)
        self.assertEqual(saved['terrainPoints'][0], source['terrainPoints'][0])
        self.assertEqual([e['id'] for e in saved['customElements']], [0, 1])
        self.assertEqual([e['state']['difficulty'] for e in saved['customElements']], [0, 1])
        self.assertEqual(saved['customElements'][0]['state']['extraField'], 'keep')
        self.assertNotIn('opponents', saved['cityProperties']['circuitRaces'][0])
        data = exported(saved)
        with tempfile.TemporaryDirectory() as directory:
            old, new = Path(directory)/'old', Path(directory)/'new'
            old.mkdir(); new.mkdir()
            CinfoAimapExporter(SimpleNamespace(data=source), False).export_race(str(old), race, 'circuit0')
            CinfoAimapExporter(SimpleNamespace(data=data), False).export_race(str(new), data['cityProperties']['circuitRaces'][0], 'circuit0')
            self.assertEqual({p.name:p.read_bytes() for p in old.iterdir()}, {p.name:p.read_bytes() for p in new.iterdir()})

    def test_empty_professional_falls_back_and_incomplete_routes_survive(self):
        car = opponent(); car['waypoints'] = []
        saved = migration.migrate_city(dict(cityProperties=dict(circuitRaces=[dict(opponents=dict(opponents=[car]))])))
        data = exported(saved)
        race = data['cityProperties']['circuitRaces'][0]
        self.assertEqual(saved['lowLevelElements'][0]['points']['spline'], [])
        self.assertEqual(opponents(data, race, True), opponents(data, race, False))

    def test_normal_migration_backup_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'preferences.json').write_text(json.dumps(dict(coreVersion=4)))
            (root/'presets.json').write_text(json.dumps(dict(presets={})))
            with gzip.open(root/'city.json.gz', 'wt') as stream:
                json.dump(dict(cityProperties=dict(circuitRaces=[dict(opponents=dict(opponents=[opponent()]))])), stream)
            before = (root/'city.json.gz').read_bytes()
            migration.process_folder(MigrationHelper(directory+'/'))
            self.assertEqual((root/'city.json.gz.v4.bak').read_bytes(), before)
            self.assertEqual(json.loads((root/'preferences.json').read_text())['coreVersion'], 5)
            after = (root/'city.json.gz').read_bytes()
            migration.process_folder(MigrationHelper(directory+'/'))
            self.assertEqual((root/'city.json.gz').read_bytes(), after)

    def test_invalid_ownership_is_reported(self):
        data = dict(cityProperties=dict(circuitRaces=[dict(_elementContainerId='duplicate'),dict(_elementContainerId='duplicate')]),
                    customElements=[dict(id=1,type='opponent',data=dict(name='Unassigned opponent',fields=dict(state={})))],
                    meshInstances=[dict(id=2,name='Orphaned prop',settings=dict(_propertyContainerId='missing'))])
        with patch('race_elements.report.error') as error:
            validate_ownership(data)
            self.assertEqual(error.call_count, 3)
            self.assertEqual(error.call_args.kwargs['element'], 'Orphaned prop')

    def test_race_paths_are_separate_and_archived_and_cleaned(self):
        data = dict(cityProperties=dict(circuitRaces=[dict(_elementContainerId='A'), dict(_elementContainerId='B')]))
        parts = []
        for owner in ('', 'A', 'A', 'B'):
            element = line(2.5)
            if owner:
                element['data']['fields']['state']['_propertyContainerId'] = owner
            export_prop_placer(SimpleNamespace(data=data), element, parts)
        # A polygon/strip contributes the exact evaluated individual placements.
        element = dict(id=9, type='propPolygon', data=dict(name='Scatter', fields=dict(state=dict(_propertyContainerId='B')),
            propLines=[dict(props=[dict(meshId=0,position=[3,4,5],rotation=[0,0,0,1],scale=[1,1,1])])]))
        export_prop_placer(SimpleNamespace(data=dict(meshDict=[dict(name='geometry/cone.pkg')])), element, parts)
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory); layout = OutputLayout(str(root/'test.psdl'))
            scene = Scene(parts)
            PATHSETWriter(scene, layout.psdl).write()
            write_props(scene, data, layout)
            global_paths = read_paths(root/'city/test/props.pathset')
            paths_a = read_paths(root/'race/test/circuit0.pathset')
            paths_b = read_paths(root/'race/test/circuit1.pathset')
            self.assertEqual(len(global_paths), 1)
            self.assertEqual(len(paths_a), 2)
            self.assertTrue(all(p[1:3] == (2,10) for p in paths_a))
            self.assertEqual(sorted(p[1] for p in paths_b), [1,2])
            individual = next(p for p in paths_b if p[1] == 1)
            self.assertEqual(individual[3][0], (-3.0,4.0,5.0))
            archive = root/'test.ar'
            ArPacker(layout, str(root/'assets'), False).pack(str(archive))
            with zipfile.ZipFile(archive) as stream:
                self.assertIn('race/test/circuit0.pathset', stream.namelist())
                self.assertIn('race/test/circuit1.pathset', stream.namelist())
                self.assertFalse(any('.km2-' in name for name in stream.namelist()))
            (root/'race/test/custom.pathset').write_bytes(b'keep')
            data['cityProperties']['circuitRaces'] = [dict(_elementContainerId='B')]
            write_props(scene, data, layout)
            self.assertFalse((root/'race/test/circuit1.pathset').exists())
            self.assertEqual((root/'race/test/custom.pathset').read_bytes(), b'keep')
            self.assertEqual(sorted(p[1] for p in read_paths(root/'race/test/circuit0.pathset')), [1,2])
            data['cityProperties']['circuitRaces'] = []
            write_props(scene, data, layout)
            self.assertFalse((root/'race/test/circuit0.pathset').exists())
            self.assertEqual((root/'race/test/custom.pathset').read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()
