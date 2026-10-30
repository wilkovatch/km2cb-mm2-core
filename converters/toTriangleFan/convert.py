# Converts triangle fans, road triangle fans and roof triangle fans to each other (see exporters/psdl/custom_element_conversion.py)
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'exporters', 'psdl'))
import custom_element_conversion as cec

cec.run(sys.argv, lambda data: (cec.convert_fans(data, "triangleFan"), None))
