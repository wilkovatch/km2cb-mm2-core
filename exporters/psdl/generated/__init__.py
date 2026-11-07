"""The files generated from the elements of the city (the low LOD textures of the roads, the models of the bridges).

The same code makes them in the editor, through the generators of the core (generators/, in a cache folder of the
program, to preview them) and in the export (generated_export.py, in the export folder): they are never written in the
folder of the city. The names hold a hash of the contents, so that equal results share one file and the editor never
shows a cached file for a changed result.
"""
import json
import os
from pathlib import Path

CORE = Path(__file__).resolve().parents[3]


class GenerationError(Exception):
    # its message is a string key of the core (strings/en-US.json)
    pass


_strings = None


def message(key):
    """The English text of a string key of the core, the key itself if it's not one."""
    global _strings
    if _strings is None:
        try:
            with open(CORE / 'strings' / 'en-US.json', encoding='utf-8') as f:
                _strings = json.load(f)
        except (OSError, ValueError):
            _strings = {}
    return _strings.get(key, key)


class OutputRoot:
    """A folder laid out as the game folder (geometry, texture, bound, tune), where the generated files are written.

    It records the files written (with whether they were there before, see generated_export.py) and keeps the results
    already computed, so that what several elements share (e.g. the low LOD texture of a road under a bridge) is made once.
    """

    def __init__(self, root):
        self.root = str(root)
        self.files = {}  # path relative to the root -> it existed before being written
        self.memo = {}

    def path(self, relative):
        full = os.path.join(self.root, *relative.split('/'))
        if relative not in self.files:
            self.files[relative] = os.path.exists(full)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        return full
