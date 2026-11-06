# The helpers of the converters of the core (see the converters folder): they get the elements in the format of the
# export JSON and write custom elements in the format read by the program (see the Core Custom Elements page of the
# wiki), with the exporter (json_processor.py) at hand to process the elements as they are exported.

import json
from json_processor import JsonProcessor


class ConversionError(Exception):
    # its message is a string key shown to the user
    pass


class Output:
    # the custom elements (and their points) in the format read by the program (see Operations.Conversion)
    def __init__(self):
        self.points = []
        self.point_ids = {}
        self.elements = []
        self.updates = []

    def point(self, position, weld=True):
        # the same position is the same point (shared by the elements)
        key = tuple(round(float(c), 3) for c in position)
        if key in self.point_ids:
            return self.point_ids[key]
        pid = "p" + str(len(self.points))
        self.points.append({"id": pid, "position": [float(c) for c in position], "weld": weld})
        self.point_ids[key] = pid
        return pid

    def element(self, typ, name, state=None, points=None, mesh=None, container=None, source=None):
        eid = "e" + str(len(self.elements))
        e = {"id": eid, "type": typ, "name": name, "state": state or {}}
        if points is not None:
            e["points"] = points
        if mesh is not None:
            e["mesh"] = mesh
        if container is not None:
            e["container"] = container
        if source is not None:
            e["source"] = source
        self.elements.append(e)
        return eid

    def update(self, element, points=None, state=None):
        # changes of an existing element (element: its reference, {"kind": "customElement", "id": id}): the points given
        # replace its points of the same names, the state given is merged into its state
        u = {"element": element}
        if points is not None:
            u["points"] = points
        if state is not None:
            u["state"] = state
        self.updates.append(u)

    def write(self, path, replace=None):
        res = {"points": self.points, "elements": self.elements}
        if len(self.updates) > 0:
            res["updates"] = self.updates
        if replace is not None:
            res["replace"] = replace
        with open(path, 'w') as f:
            json.dump(res, f)


class Converter:
    # the input of a converter with the exporter on it (jp, after its reset: manual_blocks are the blocks set by hand)
    def __init__(self, data):
        self.data = data
        self.prepare()
        self.jp = JsonProcessor(data, False, ignore_blocks=True)
        self.manual_blocks = self.jp.reset()

    # The ids of the input are the ones of the program: they become the indices of the lists (as in the export JSON,
    # which the exporter expects), the references of the output use the ones of the program again

    def prepare(self):
        data = self.data
        self.original_ids = {}
        maps = {}
        for kind in ('roads', 'intersections', 'terrainPatches', 'buildingLines'):
            maps[kind] = {}
            for i, e in enumerate(data.get(kind) or []):
                maps[kind][e['id']] = i
                self.original_ids[(kind, i)] = e['id']
                e['id'] = i
        rmap, imap = maps['roads'], maps['intersections']
        for r in data.get('roads') or []:
            r['startIntersectionId'] = imap.get(r['startIntersectionId'], -1)
            r['endIntersectionId'] = imap.get(r['endIntersectionId'], -1)
        for i in data.get('intersections') or []:
            i['roads'] = [rmap.get(r, -1) for r in i['roads']]
        self.maps = maps

    def original_id(self, kind, index):
        return self.original_ids.get((kind, index))

    def find(self, kind, original_id):
        index = self.maps[kind].get(original_id)
        return None if index is None else self.data[kind][index]


def run(argv, convert):
    # argv: the Files/python folder, the input JSON, the output JSON; convert(data) returns (Output, replace)
    import sys
    sys.path.append(argv[1])
    import DecodeExportedJson
    data = DecodeExportedJson.DecodeExportedJson().decode_json(argv[2])
    try:
        out, replace = convert(data)
    except ConversionError as e:
        sys.exit(str(e))
    out.write(argv[3], replace)
