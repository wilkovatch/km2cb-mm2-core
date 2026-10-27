"""Puts each group of building parts (low-level elements) in the PSDL room found at its location, as the exporter
would: the group is merged into the room (its parts move into it and the group is deleted). The groups whose location
is in a block of a procedural element, or in no block, are left as they are."""
import contextlib
import io
import os
import sys
import tempfile

import citybuilder as cb
from citybuilder import api

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(CORE, 'exporters', 'psdl'))
import DecodeExportedJson  # noqa: E402 (Files/python is on the path of the scripts)
from json_processor import JsonProcessor  # noqa: E402
from low_level import position  # noqa: E402

folder = tempfile.mkdtemp(prefix='km2_rooms_')
path = os.path.join(folder, 'city.json')
cb.progress(0.1, "Reading the city")
api.city.exportJson(path=path)
data = DecodeExportedJson.DecodeExportedJson().decode_json(path)
os.remove(path)
os.rmdir(folder)

cb.progress(0.5, "Finding the rooms")
jp = JsonProcessor(data, False)
with contextlib.redirect_stdout(io.StringIO()):
    jp.get_objects()
rooms_by_block = {block: room for room, block in jp.low_level.room_blocks.items()}

# the ids of the export are the indices of the elements, in the order of the program
listed = api.elements.list(kind="lowLevel")
elements = data.get('lowLevelElements') or []
if len(listed) != len(elements):
    raise Exception("the low-level elements changed while reading the city")

merged = 0
left = 0
for e in elements:
    if e['type'] != 'buildingGroup':
        continue
    points = e.get('points') or {}
    block = jp.find_block(position(points['location'])) + 1 if 'location' in points else 0
    if block <= 0 and 'frontLocation' in points:
        block = jp.find_block(position(points['frontLocation'])) + 1
    room = rooms_by_block.get(block)
    if room is None:
        left += 1
        continue
    api.lowLevel.merge(**{"from": listed[e['id']]["id"], "into": listed[room]["id"]})
    merged += 1

cb.alert("%d groups of building parts merged into rooms, %d left (not in a PSDL room)" % (merged, left), "Assign building parts to rooms")
