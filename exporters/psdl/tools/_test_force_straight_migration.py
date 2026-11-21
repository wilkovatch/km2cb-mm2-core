"""Synthetic checks for the version-11 migration: the force straight sidewalk flags of the roads become sidewalk overrides
of the intersections (one outer segment skipping the crosswalks), on the sidewalks they straightened."""
import gzip
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

CORE = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE.parents[1] / 'python')]

import MigrationHelper

spec = importlib.util.spec_from_file_location('force_straight_migration', CORE / 'migrations/11.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def p(x, z):
    return dict(x=x, y=0.0, z=z)


def road(rid, points, start=-1, end=-1, flags=None):
    return dict(id=rid, name='Road %d' % (rid + 1), state=dict(type='psdl'), instanceState=dict(flags or {}, segments=10),
                points=points, startIntersectionId=start, endIntersectionId=end)


def city(roads):
    return dict(roads=roads, intersections=[dict(id=0, name='Intersection 1', roads=[r['id'] for r in roads], center=p(0, 0),
                                                 state=dict(type='psdl', sidewalkSegments=4))])


def t_junction(flags=None):
    """A T (+z north, +x east): road 0 ends from the west, road 1 starts to the east, road 2 ends from the south.
    Clockwise from above the order is 0, 1, 2: the sidewalks are 0-1 (north, a straight side), 1-2 (south east) and
    2-0 (south west), each with the index of its first road."""
    flags = flags or {}
    return city([road(0, [p(-100, 0), p(0, 0)], end=0, flags=flags.get(0)),
                 road(1, [p(0, 0), p(100, 0)], start=0, flags=flags.get(1)),
                 road(2, [p(0, -100), p(0, 0)], end=0, flags=flags.get(2))])


def bend(flags=None):
    """Road 0 ends from the west, road 1 starts to the south: sidewalk 0-1 is the outer (convex) corner, 1-0 the inner one."""
    flags = flags or {}
    return city([road(0, [p(-100, 0), p(0, 0)], end=0, flags=flags.get(0)),
                 road(1, [p(0, 0), p(0, -100)], start=0, flags=flags.get(1))])


def sidewalks(c):
    return (c['intersections'][0].get('instanceState') or {}).get('sidewalks')


def straightened(source):
    return [s['road'] for s in sidewalks(migration.migrate_city(source)[0]) or []]


class Migration(unittest.TestCase):
    def test_order_and_convex_corners(self):
        def directions(c):
            return [migration.direction_to_center(r, 0, p(0, 0)) for r in c['roads']]
        t = directions(t_junction())
        self.assertEqual(migration.clockwise_order(t), [0, 1, 2])
        self.assertFalse(any(migration.is_convex(t[i], t[(i + 1) % 3]) for i in range(3)))
        b = directions(bend())
        self.assertEqual(migration.clockwise_order(b), [0, 1])
        self.assertTrue(migration.is_convex(b[0], b[1]))
        self.assertFalse(migration.is_convex(b[1], b[0]))

    def test_end_flags(self):
        # road 2 ends here, heading north: its left is the south west sidewalk (from road 2), its right the south east one
        c, changed = migration.migrate_city(t_junction({2: dict(forceStraightLeftEndSidewalk=True)}))
        self.assertEqual(sidewalks(c), [dict(road=2, innerSegments=4, outerSegments=1, outerSkipsCrosswalks=True)])
        self.assertEqual(changed, ['Intersection 1'])
        self.assertEqual(straightened(t_junction({2: dict(forceStraightRightEndSidewalk=True)})), [1])

    def test_start_flags_where_they_had_effect(self):
        # road 1 starts here, heading east: the junction read its Left flag for the south east sidewalk (from road 1)
        # and its Right flag for the north one (from road 0), the opposite sides of their names
        self.assertEqual(straightened(t_junction({1: dict(forceStraightLeftStartSidewalk=True)})), [1])
        self.assertEqual(straightened(t_junction({1: dict(forceStraightRightStartSidewalk=True)})), [0])
        # the flags of the other end don't count
        self.assertEqual(straightened(t_junction({1: dict(forceStraightLeftEndSidewalk=True)})), [])

    def test_convex_corners_unchanged(self):
        c, changed = migration.migrate_city(bend({0: dict(forceStraightLeftEndSidewalk=True)}))
        self.assertIsNone(sidewalks(c))
        self.assertEqual(changed, [])
        self.assertEqual(straightened(bend({0: dict(forceStraightRightEndSidewalk=True)})), [1])

    def test_flags_removed_and_overrides_kept(self):
        # the right of road 0 and the left of road 2 are the same (south west) sidewalk
        source = t_junction({0: dict(forceStraightRightEndSidewalk=True), 2: dict(forceStraightLeftEndSidewalk=True)})
        source['intersections'][0]['instanceState'] = dict(sidewalks=[
            dict(road=2, innerSegments=7, outerSegments=3, outerSkipsCrosswalks=False),
            dict(road=0, innerSegments=2, outerSegments=0, outerSkipsCrosswalks=False)])
        c, _ = migration.migrate_city(source)
        self.assertEqual(sidewalks(c), [dict(road=0, innerSegments=2, outerSegments=0, outerSkipsCrosswalks=False),
                                        dict(road=2, innerSegments=7, outerSegments=1, outerSkipsCrosswalks=True)])
        for r in c['roads']:
            self.assertFalse(any(k.startswith('forceStraight') for k in r['instanceState']))
            self.assertEqual(r['instanceState']['segments'], 10)
        self.assertIn('forceStraightRightEndSidewalk', source['roads'][0]['instanceState'])  # the source is not changed

    def test_geometryless_roads_left_out(self):
        # without geometry, road 2 has no sidewalks: the T has only the north (0-1) and south (1-0) sidewalks
        source = t_junction({0: dict(forceStraightLeftEndSidewalk=True)})
        source['roads'][2]['state']['type'] = 'bai'
        self.assertEqual(straightened(source), [0])
        source['roads'][1]['instanceState']['forceStraightLeftStartSidewalk'] = True
        self.assertEqual(straightened(source), [0, 1])

    def test_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            with gzip.open(folder / 'city.json.gz', 'wt', encoding='utf-8') as f:
                json.dump(t_junction({2: dict(forceStraightLeftEndSidewalk=True)}), f)
            (folder / 'preferences.json').write_text(json.dumps(dict(coreVersion=10)), encoding='utf-8')
            migration.process_folder(MigrationHelper.MigrationHelper(str(folder) + '/'))
            with gzip.open(folder / 'city.json.gz', 'rt', encoding='utf-8') as f:
                self.assertEqual([s['road'] for s in sidewalks(json.load(f))], [2])
            self.assertEqual(json.loads((folder / 'preferences.json').read_text(encoding='utf-8'))['coreVersion'], 11)
            self.assertTrue((folder / 'city.json.gz.v10.bak').is_file())
            # a city already at version 11 is left as it is
            (folder / 'city.json.gz.v10.bak').unlink()
            migration.process_folder(MigrationHelper.MigrationHelper(str(folder) + '/'))
            self.assertFalse((folder / 'city.json.gz.v10.bak').exists())


if __name__ == '__main__':
    unittest.main()
