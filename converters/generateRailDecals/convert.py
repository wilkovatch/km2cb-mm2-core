"""Generate independent decal elements across selected intersections, without changing the roads or intersection."""
import copy
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'exporters/psdl'))
import low_level_conversion as llc
from common.bai_writer import BAIWriter, RouteGeometry, resampled_parameters, section_frames, normalized


def convert(data):
    converter = llc.Converter(copy.deepcopy(data))
    out = llc.Output()
    for target in data['convert']:
        intersection = converter.find('intersections', target['id'])
        if intersection is None:
            raise llc.ConversionError('CONVERSION_ERROR_MISSING')
        ends = []
        for rid in intersection['roads']:
            road = converter.data['roads'][rid]
            state = road['data']['fields']['state']
            if not state.get('cableCarLine'):
                continue
            converter.jp.get_element_parts('road', road, converter.manual_blocks)
            record = converter.jp.exported_roads.get(rid)
            if record is None:
                continue
            sections = converter.jp.get_bai_sections(record, False)
            if len(sections) < 2:
                continue
            # Work in the same z-up scene coordinates and with the same resampling as the BAI writer.
            sections = [[np.array([p[0], p[2], p[1]]) for p in section] for section in sections]
            geo = RouteGeometry()
            geo.right_outer = [s[0] for s in sections]
            geo.right_curb = [s[1] for s in sections]
            geo.left_curb = [s[-2] for s in sections]
            geo.left_outer = [s[-1] for s in sections]
            geo = geo.resampled(resampled_parameters(geo.centre()))
            centre = geo.centre()
            xs, _, _, _ = section_frames(centre)
            offset = converter.jp.get_cable_car_offset(state)
            at_end = road['endIntersectionId'] == intersection['id']
            index, neighbor = (-1, -2) if at_end else (0, 1)
            heading = normalized(centre[index] - centre[neighbor])
            rails = [centre[index] + xs[index] * offset, centre[index] - xs[index] * offset]
            ends.append((heading, rails, {}))
        for i, (curve, _) in enumerate(BAIWriter(None, '', False).join_rails(ends)):
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
    llc.run(sys.argv, convert)
