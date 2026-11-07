"""Checks of the roads and intersections without geometry (the bai road type) on the export JSON written by the
geometrylessRoads API self-test of the core (its path in KM2_GEOMETRYLESS_JSON, skipped without it): the BAI sections of
a BAI-only road are the ones of the same PSDL road, the roads and intersections without geometry are in the room of the
terrain patch under them, in the BAI network, and the one over no room is left out with a warning."""
import os
from pathlib import Path
import sys
import unittest

import numpy as np

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE / 'exporters/psdl'), str(CORE.parents[1] / 'python')]
from DecodeExportedJson import DecodeExportedJson
from json_processor import JsonProcessor
from writers import report

EXPORT_JSON = os.environ.get('KM2_GEOMETRYLESS_JSON')
TWIN_OFFSET = (0.0, 0.0, 50.0)  # of the BAI-only twin from the PSDL one (see ApiSelfTest.GeometrylessRoads.cs)


@unittest.skipUnless(EXPORT_JSON, 'KM2_GEOMETRYLESS_JSON is not set')
class GeometrylessRoadsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = DecodeExportedJson().decode_json(EXPORT_JSON)
        cls.warnings = []
        old = report.warning, report.collecting
        # the warnings collected here, the errors raised (not collected by the ExportReport of the program)
        report.warning = lambda message, **kwargs: cls.warnings.append((message, kwargs))
        report.collecting = lambda: False
        try:
            cls.jp = JsonProcessor(cls.data, False)
            cls.jp.get_objects(traffic_only=True)
        finally:
            report.warning, report.collecting = old

    def road(self, name):
        return next(r for r in self.data['roads'] if r['data']['name'] == name)

    def geometryless_roads(self):
        return [r for r in self.data['roads'] if r['data']['fields'].get('geometryless')]

    def patch_room(self):
        patch = self.data['terrainPatches'][0]
        return self.jp.element_blocks[('terrainPatch', patch['id'])]

    def test_same_bai_sections_as_psdl(self):
        expected = self.jp.exported_roads[self.road('Twin psdl')['id']]['bai_sections']
        actual = self.jp.get_geometryless_bai_sections(self.road('Twin bai')['data']['fields'])
        self.assertGreater(len(expected), 2)
        self.assertEqual(len(actual), len(expected))
        for a, e in zip(actual, expected):
            self.assertEqual(len(a), len(e))  # outer edges, curbs and divider
            a = np.subtract(a, TWIN_OFFSET)
            np.testing.assert_allclose(a[:, [0, 2]], np.array(e)[:, [0, 2]], atol=1e-3)
            # the road of a psdl road with sidewalks is lower than them (0.15 m), the BAI-only road has no heights
            np.testing.assert_allclose(a[:, 1], np.array(e)[:, 1], atol=0.16)

    def test_roads_in_the_room_under_them(self):
        room = self.patch_room()
        square = [r for r in self.geometryless_roads() if r['startIntersectionId'] != -1 and r['endIntersectionId'] != -1]
        self.assertEqual(len(square), 4)
        for road in square:
            rec = self.jp.exported_roads[road['id']]
            self.assertIsNone(rec['elem'])
            self.assertEqual(rec['rooms'], [room])
            self.assertIsNotNone(self.jp.network.road_of.get(road['id']))

    def test_intersections_in_the_room_under_them(self):
        room = self.patch_room()
        without = [obj for obj in self.jp.traffic_intersections if obj[0] is None]
        self.assertEqual(len(without), 4)
        self.assertTrue(all(obj[2] == room and obj[1]['data']['fields']['geometryless'] for obj in without))
        names = set(obj[1]['data']['name'] for obj in without)
        self.assertEqual(names, set(node.name for node in self.jp.network.intersections if node.room == room))
        shared = [w for w in self.warnings if w[1].get('kind') == 'intersection' and w[1].get('element') in names]
        self.assertEqual(len(shared), 3)  # all but the first one in the room

    def test_road_over_no_room(self):
        lonely = self.road('Lonely BAI road')
        self.assertNotIn(lonely['id'], self.jp.exported_roads)
        self.assertTrue(any(w[1].get('element') == 'Lonely BAI road' for w in self.warnings))

    def test_mixed_intersection(self):
        # the PSDL intersection with a BAI-only road: a surface between the PSDL roads only, the BAI-only road ends free
        mixed = [i for i in self.data['intersections'] if len(i['roads']) == 4]
        self.assertEqual(len(mixed), 1)
        fields = mixed[0]['data']['fields']
        self.assertEqual(len(fields['sortOrder']), 4)
        self.assertEqual(len(fields['geometrySortOrder']), 3)
        self.assertTrue(any(obj[1] is mixed[0] and obj[0] is not None for obj in self.jp.traffic_intersections))


if __name__ == '__main__':
    unittest.main()
