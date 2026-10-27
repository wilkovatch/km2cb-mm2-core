# Sets the perimeter of rooms to the one the export computes from their attributes when they have none (see
# exporters/psdl/low_level_conversion.py), so that it can be edited
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'exporters', 'psdl'))
import low_level_conversion as llc

llc.run(sys.argv, lambda data: (llc.room_perimeter(data), False))
