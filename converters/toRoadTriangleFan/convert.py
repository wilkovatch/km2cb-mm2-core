# Converts triangle fans, road triangle fans and roof triangle fans to each other (see exporters/psdl/low_level_conversion.py)
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'exporters', 'psdl'))
import low_level_conversion as llc

llc.run(sys.argv, lambda data: (llc.convert_fans(data, "roadTriangleFan"), None))
