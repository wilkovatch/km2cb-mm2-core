"""The models of the movable bridges with generateMesh, for the editor (see the Core Generators page of the builder's wiki).

The program runs this when the bridge or the roads it's attached to change: the model is made by generated/bridge_mesh.py
in the cache folder of the program (outputFolder), as the exporter makes it in the export folder. The values (the path
of the model and the length of a leaf) are given to lua/bridges.lua as ctx.generated.
"""
import json
import os
from pathlib import Path
import sys

CORE = Path(__file__).resolve().parents[2]
sys.path.append(str(CORE / 'exporters' / 'psdl'))


def generate(data):
    from generated import OutputRoot, GenerationError, bridge_mesh
    out = OutputRoot(data['outputFolder'])
    folders = data.get('searchFolders') or [data['cityFolder']]
    results = []
    for target in data['generate']:
        result = {'element': target}
        element = next((e for e in data.get('customElements') or [] if e['id'] == target['id']), None)
        try:
            if element is None:
                raise GenerationError('GENERATION_ERROR_MISSING')
            path, length = bridge_mesh.generate(element, data, out, folders)
            result['values'] = {'mesh': os.path.join(out.root, *path.split('/')).replace('\\', '/'), 'length': length}
        except GenerationError as e:
            result['error'] = str(e)
        results.append(result)
    return {'results': results}


if __name__ == '__main__':
    # the Files/python folder, the input JSON, the output JSON
    sys.path.append(sys.argv[1])
    import DecodeExportedJson
    output = generate(DecodeExportedJson.DecodeExportedJson().decode_json(sys.argv[2]))
    with open(sys.argv[3], 'w') as f:
        json.dump(output, f)
