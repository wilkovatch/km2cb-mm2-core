"""Generate independent decal elements across selected intersections, without changing the roads or intersection."""
import copy
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'exporters/psdl'))
import custom_element_conversion as cec
from traffic.rails import join_rails
from writers.bai_writer import Route, normalized


def convert(data):
    converter = cec.Converter(copy.deepcopy(data))
    out = cec.Output()
    for target in data['convert']:
        intersection = converter.find('intersections', target['id'])
        if intersection is None:
            raise cec.ConversionError('CONVERSION_ERROR_MISSING')
        ends = []
        for rid in intersection['roads']:
            road = converter.data['roads'][rid]
            if not road['data']['fields']['state'].get('cableCarLine'):
                continue
            converter.jp.get_element_parts('road', road, converter.manual_blocks)
            bai_road = converter.jp.traffic.single_road(rid)
            if bai_road is None:
                continue
            # the rails as exported in the BAI (in the z-up space of the writer)
            route = Route(bai_road)
            at_end = road['endIntersectionId'] == intersection['id']
            index, neighbor = (-1, -2) if at_end else (0, 1)
            heading = normalized(route.centre[index] - route.centre[neighbor])
            rails = [route.right.rail[index], route.left.rail[index]]
            ends.append((heading, rails, {}))
        for i, (curve, _) in enumerate(join_rails(ends)):
            if not any(np.linalg.norm(p - curve[0]) > 0.001 for p in curve[1:]):
                continue
            ids = []
            for p in curve:
                pid = 'p' + str(len(out.points))
                out.points.append(dict(id=pid,position=[float(p[0]),float(p[2]),float(p[1])],weld=False))
                ids.append(pid)
            out.element('decal', intersection['data']['name'] + ' rail ' + str(i + 1),
                        state={'texture': 'texture/r4i_rails_f.tex', 'width': 2.0, 'curveType': 2},
                        points={'spline': ids})
    return out, False


if __name__ == '__main__':
    cec.run(sys.argv, convert)
