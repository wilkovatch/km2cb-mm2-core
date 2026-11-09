"""The generated files of the city in the export (see generated/): the low LOD textures of the roads with
generateLodTexture and the models of the bridges with generateMesh, written in the export folder (never in the city
folder) before the other files. Their paths go in the data of the city, as if chosen in the editor, so that the writers
export them as the others.

.km2-generated.json in the export folder lists the files the exports wrote there (not the ones that were already there,
even with the same name): an export writing both kinds of files removes the listed ones it no longer writes.
"""
import json
from pathlib import Path

from generated import OutputRoot, GenerationError, message
from writers import report
from utils import state_bool

MANIFEST = '.km2-generated.json'
FOLDERS = ('geometry', 'bound', 'texture', 'tune')
GENERATED_MODEL = '_generatedModel'  # in the state of a bridge whose model was generated here
GENERATION_ERROR = '_generationError'  # the reason it wasn't, the bridge isn't exported (see bridge_export.get_bridges)


def search_folders(data, common_dir):
    # where the textures are looked for, as in the editor (older programs don't give them)
    folders = data.get('searchFolders')
    if folders:
        return list(folders)
    return [folder for folder in (data.get('cityFolder'), common_dir) if folder]


class GeneratedExport:
    def __init__(self, root, data, common_dir):
        self.out = OutputRoot(root)
        self.data = data
        self.folders = search_folders(data, common_dir)
        self.passes = set()

    def lod_textures(self):
        self.passes.add('lod')
        # the roads, and the pieces of road through the intersections (with the state of the road they continue)
        candidates = list(self.data.get('roads') or [])
        for intersection in self.data.get('intersections') or []:
            if not intersection.get('ghost'):
                candidates += intersection.get('roadsThrough') or []
        roads = [r for r in candidates if not r.get('ghost') and state_bool(r['data']['fields']['state'], 'generateLodTexture')]
        if not roads:
            return
        from generated import lod_texture  # it needs Pillow and numpy, the city may not need them
        for road in roads:
            state = road['data']['fields']['state']
            if not lod_texture.enabled(state):
                continue
            name = road['data'].get('name', '')
            try:
                state['textureLOD'] = lod_texture.generate(state, self.out, self.folders)
            except GenerationError as e:
                report.warning('the low LOD texture of the road ' + name + ' was not generated: ' + message(str(e)), element=name, kind='road')

    def bridge_models(self):
        self.passes.add('bridges')
        bridges = [e for e in self.data.get('customElements') or [] if e.get('type') == 'bridge' and state_bool(e['data']['fields']['state'], 'generateMesh')]
        if not bridges:
            return
        from generated import bridge_mesh
        for element in bridges:
            state = element['data']['fields']['state']
            try:
                state['mesh'], _ = bridge_mesh.generate(element, self.data, self.out, self.folders)
                state[GENERATED_MODEL] = True
            except GenerationError as e:
                state[GENERATION_ERROR] = message(str(e))

    def finish(self):
        root = Path(self.out.root)
        manifest = root / MANIFEST
        try:
            previous = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else []
        except (OSError, ValueError):
            previous = []
        previous = [p for p in previous if isinstance(p, str) and safe(p)] if isinstance(previous, list) else []
        written = self.out.files
        owned = {path for path, existed in written.items() if not existed or path in previous}
        if self.passes >= {'lod', 'bridges'}:
            # every generated file was written again if still needed
            for path in previous:
                if path not in written:
                    (root / path).unlink(missing_ok=True)
        else:
            owned |= set(previous)
        if owned or previous:
            temporary = manifest.with_suffix('.tmp')
            temporary.write_text(json.dumps(sorted(owned)), encoding='utf-8')
            temporary.replace(manifest)


def safe(path):
    # a file of the generated folders, relative to the export folder
    parts = path.split('/')
    return len(parts) >= 2 and parts[0] in FOLDERS and all(part not in ('', '.', '..') and '\\' not in part and ':' not in part for part in parts)
