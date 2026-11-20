"""Draws where the ambient cars go at the intersections and the paths they take through them, as the game drives them
(see traffic/ambient.py of the exporter): an info item per lane arriving at the intersection, with its paths. Run by the
program (the check:trafficPaths button of the intersections) with the export JSON of the city, whose "check" has the
targets ({"kind": "intersection", "id": <index>})."""
from pathlib import Path
import sys

sys.path.append(sys.argv[1])
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'exporters/psdl'))

import DecodeExportedJson
import ExportReport as report
from json_processor import JsonProcessor
from traffic.ambient import IntersectionTraffic, LEFT, RIGHT, STRAIGHT, U_TURN
from utils import state_val

COLOURS = {RIGHT: '#2e86de', STRAIGHT: '#2e9e44', LEFT: '#e67e22', U_TURN: '#d62828'}
TURN_NAMES = {RIGHT: 'right', STRAIGHT: 'straight on', LEFT: 'left', U_TURN: 'U-turn'}


def lane_number(road, side, lane, drive_on_left):
    # the number of a lane from the centre of the road, 1 the inner one: with left-hand traffic the game's lane 0 is
    # the outer one (see GameRoad.drive_on_left)
    return road.count[side] - lane if drive_on_left else lane + 1


def lane_name(road, side, lane, drive_on_left):
    count = road.count[side]
    number = lane_number(road, side, lane, drive_on_left)
    text = 'lane ' + str(number) + ' of ' + str(count)
    if count > 1 and number == 1:
        text += ' (inner)'
    elif count > 1 and number == count:
        text += ' (outer)'
    return text


def lane_text(result, drive_on_left):
    road, side, lane = result.road, result.side, result.lane
    text = road.road.name + ', ' + lane_name(road, side, lane, drive_on_left) + ': '
    if not result.moves:
        return text + 'no road'
    moves = [TURN_NAMES[m.turn] + ' to ' + m.road.road.name + ' (lane '
             + str(lane_number(m.road, m.side, m.driven_lane(), drive_on_left)) + ')' for m in result.moves]
    text += ', '.join(moves)
    if len(moves) > 1:
        text += ', at random'
    return text


def main():
    data = DecodeExportedJson.DecodeExportedJson().decode_json(sys.argv[2])
    report.init(data)
    targets = [t for t in ((data.get('check') or {}).get('targets') or []) if t.get('kind') == 'intersection']
    if not targets:
        report.info('No intersections to check')
        return
    jp = JsonProcessor(data, False)
    jp.get_objects(traffic_only=True)
    if jp.network is None:
        report.error('The traffic was not exported')
        return
    roads = {}
    drive_on_left = bool(state_val(data.get('cityProperties'), 'driveOnLeft', False))
    for target in targets:
        intersection = data['intersections'][target['id']]
        name = intersection['data']['name']
        # a BAI intersection, or the ring of them replacing an intersection with too many roads
        nodes = [n for n in jp.network.intersections if n.name == name or n.name.startswith(name + ' [BAI ')]
        if not nodes:
            report.info('Not an intersection of the traffic: the cars drive through it (a seamless intersection) or none '
                        'arrives', element=name, kind='intersection', position=[float(c) for c in intersection['center']])
            continue
        lanes = []
        for node in nodes:
            lanes += IntersectionTraffic(node, roads, drive_on_left).lanes()
        if not lanes:
            # the roads are BAI roads only with intersections at both ends (of the row of roads joined by seamless
            # intersections they belong to)
            report.info('No cars arrive at the intersection: its roads have no lanes towards it, or don\'t end on '
                        'intersections at both ends', element=name, kind='intersection',
                        position=[float(c) for c in intersection['center']])
        for result in lanes:
            overlay = [{'type': 'polyline', 'points': m.points, 'color': COLOURS[m.turn]} for m in result.moves]
            position = result.moves[0].points[0] if result.moves else None
            report.info(lane_text(result, drive_on_left), element=name, kind='intersection', code='traffic_lane',
                        position=position, overlay=overlay)
            lane = lane_name(result.road, result.side, result.lane, drive_on_left)
            for code, message in result.problems:
                report.warning(result.road.road.name + ', ' + lane + ': ' + message, element=name, kind='intersection',
                               code=code, position=position, overlay=overlay)


if __name__ == '__main__':
    main()
