from writers.file_io import BinaryFileHelper

# the routes of the moving objects of the city (trains, boats...): a pathset with a line strip for each route, the
# points are the control points of the game's own interpolation
PATH_TYPE_LINE_STRIP = 2


def write_routes(filepath, routes):
    # routes: (name, points in MM2 coordinates, spacing byte); the room of the points is not used by the game
    file = BinaryFileHelper(filepath, 'wb')
    file.write_raw_string("PTH1")
    file.write_uint32(len(routes))
    file.write_uint32(0)
    for name, points, spacing in routes:
        file.write_string32(name)
        file.write_uint32(len(points))
        file.write_uint32(0)
        for p in points:
            file.write_uint32(0)
            for c in p:
                file.write_float(c)
        file.write_byte(PATH_TYPE_LINE_STRIP)
        file.write_byte(spacing)
        file.write_uint16(0)
    file.close()
