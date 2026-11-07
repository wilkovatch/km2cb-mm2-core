"""Checks whether the opponents of the races reach the finish as the game drives them (see traffic/opponents.py of the
exporter): the waypoints must be on intersections, and a single road must join consecutive ones, otherwise the opponent
drives straight, through whatever is in the way. Run by the program (the check:validateOpponents buttons) with the
export JSON of the city, whose "check" has the targets: races ({"kind": "propertyContainer", "id": <race identity>})
and opponents ({"kind": "customElement", "id": <index>})."""
from pathlib import Path
import sys

sys.path.append(sys.argv[1])
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'exporters/psdl'))

import DecodeExportedJson
import ExportReport
from json_processor import JsonProcessor
from race_elements import check_opponents


def main():
    data = DecodeExportedJson.DecodeExportedJson().decode_json(sys.argv[2])
    ExportReport.init(data)
    check = data.get('check') or {}
    jp = JsonProcessor(data, False)
    parts = jp.get_objects(traffic_only=True)
    check_opponents(data, jp, parts, check.get('targets'), summary=True)


if __name__ == '__main__':
    main()
