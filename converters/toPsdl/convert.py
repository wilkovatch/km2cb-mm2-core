# Converts roads, intersections, terrain patches and building lines to the PSDL attributes they are exported to (see
# exporters/psdl/custom_element_conversion.py): a room for each block of the element (the buildings in a group of building
# parts, put in the rooms where they are when exported), and the BAI road or intersection of the roads and intersections
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'exporters', 'psdl'))
import custom_element_conversion as cec


def convert(data):
    return cec.Converter(data).convert(data['convert']), None


cec.run(sys.argv, convert)
