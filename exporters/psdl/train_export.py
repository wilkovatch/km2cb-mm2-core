from common.file_io import BinaryFileHelper
from utils import state_val, state_vector

# the stock lines (race/london/london_train.pathset) are line strips with a spacing of 20 (5 m)
PATH_TYPE_LINE_STRIP = 2
PATH_SPACING = 20


def get_train_lines(city_properties):
    # the points (in file coordinates) of each train line with at least two points
    res = []
    for i, line in enumerate(state_val(city_properties, "trainLines", [])):
        points = []
        for p in state_val(line, "points", []):
            pdata = state_val(p, "point", None)
            if isinstance(pdata, dict):
                pos = state_vector(pdata, "localPosition")
                points.append((-pos["x"], pos["y"], pos["z"]))
        name = state_val(line, "name", "") or ("line " + str(i + 1))
        if len(points) < 2:
            print("Warning: the train line " + name + " has less than two points, it is not exported")
        else:
            res.append(points)
    return res


def export_trains(city_properties, racesubfolder, cityname):
    # the trains of the city (gizTrain in MM2): a pathset in the race folder with a line strip for each line,
    # the trains go back and forth between its first and last point
    lines = get_train_lines(city_properties)
    if len(lines) == 0:
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
