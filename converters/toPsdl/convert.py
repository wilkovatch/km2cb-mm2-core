# Converts roads, intersections, terrain patches and building lines to the PSDL attributes they are exported to (see
# exporters/psdl/low_level_conversion.py): a room for each block of the element (the buildings in a group of building
# parts, put in the rooms where they are when exported), and the BAI road or intersection of the roads and intersections
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'exporters', 'psdl'))
import low_level_conversion as llc


def convert(data):
    return llc.Converter(data).convert(data['convert']), None


llc.run(sys.argv, convert)
