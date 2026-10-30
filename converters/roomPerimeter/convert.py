# Sets the perimeter of rooms to the one the export computes from their attributes when they have none (see
# exporters/psdl/custom_element_conversion.py), so that it can be edited
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'exporters', 'psdl'))
import custom_element_conversion as cec

cec.run(sys.argv, lambda data: (cec.room_perimeter(data), False))
