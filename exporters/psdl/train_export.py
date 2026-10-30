from common.file_io import BinaryFileHelper
from common import report

# the stock lines (race/london/london_train.pathset) are line strips with a spacing of 20 (5 m)
PATH_TYPE_LINE_STRIP = 2
PATH_SPACING = 20


def get_train_lines(data):
    # Control points are the native input to MM2's own interpolation, never the editor's sampled preview.
    import math
    res = []
    for i, element in enumerate(data.get('customElements') or []):
        if element.get('type') != 'train':
            continue
        name = (element.get('data') or {}).get('name') or ('line ' + str(i + 1))
        try:
            points = [tuple(p['position']) for p in (element.get('points') or {}).get('spline') or []]
            valid = all(len(p) == 3 and all(math.isfinite(c) for c in p) for p in points)
        except (KeyError, TypeError, ValueError):
            points, valid = [], False
        if not valid:
            report.warning('the train line ' + name + ' has invalid points, it is not exported')
            continue
        if len(points) < 3:
            report.warning('the train line ' + name + ' has less than three points, it is not exported')
            continue
        if any(a == b for a,b in zip(points,points[1:])):
            report.warning('the train line ' + name + ' has invalid or zero-length spans, it is not exported')
            continue
        res.append([(-p[0],p[1],p[2]) for p in points])
    return res


def export_trains(data, racesubfolder, cityname):
    # the trains of the city (gizTrain in MM2): a pathset in the race folder with a line strip for each line,
    # the trains go back and forth between its first and last point
    lines = get_train_lines(data)
    if len(lines) == 0:
        from pathlib import Path
        Path(racesubfolder + cityname + "_train.pathset").unlink(missing_ok=True)
        return
    file = BinaryFileHelper(racesubfolder + cityname + "_train.pathset", 'wb')
    file.write_raw_string("PTH1")
    file.write_uint32(len(lines))
    file.write_uint32(0)
    for i, points in enumerate(lines):
        file.write_string32("PATH" + str(i))
        file.write_uint32(len(points))
        file.write_uint32(0)
        for p in points:
            file.write_uint32(0)  # room (not used by the game)
            for c in p:
                file.write_float(c)
        file.write_byte(PATH_TYPE_LINE_STRIP)
        file.write_byte(PATH_SPACING)
        file.write_uint16(0)
    file.close()
    print(str(len(lines)) + " train lines exported")
