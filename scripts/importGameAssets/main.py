"""Scripts-menu adapter. The reader and importer do not depend on the builder or on game assets."""
import json
from pathlib import Path

import citybuilder as cb

from _import_assets import ImportFailure, import_assets


SCRIPT = Path(__file__).resolve().parent
FILES = SCRIPT.parents[3]
DESTINATION = FILES / 'common' / SCRIPT.parents[1].name


def load_strings():
    # The script catalog uses the configured language, with en-US as the fallback.
    with (SCRIPT / 'strings' / 'en-US.json').open(encoding='utf-8') as file:
        strings = json.load(file)
    try:
        with (FILES.parent / 'settings.json').open(encoding='utf-8-sig') as file:
            language = json.load(file).get('Language', 'en-US')
        if language != 'en-US' and Path(language).name == language:
            with (SCRIPT / 'strings' / (language + '.json')).open(encoding='utf-8') as file:
                strings.update(json.load(file))
    except (OSError, ValueError, TypeError):
        pass
    return strings


def main():
    strings = load_strings()

    def text(key, **values):
        return strings[key].format(**values)

    cb.progress(0, text('MM2_IMPORT_CHECKING'))
    values = cb.inputs()

    def progress(done, total, archive, entry):
        cb.progress(done / total, text('MM2_IMPORT_PROGRESS', done=done, total=total, archive=archive, entry=entry))

    try:
        result = import_assets(values.get('gameFolder', ''), DESTINATION,
                               values.get('overwriteExisting', False), progress)
    except ImportFailure as error:
        raise SystemExit(text('MM2_IMPORT_FAILED', error=text(error.key, **error.values)))
    except Exception as error:
        raise SystemExit(text('MM2_IMPORT_FAILED', error=text('MM2_IMPORT_UNEXPECTED', detail=str(error))))
    cb.alert(text('MM2_IMPORT_SUMMARY', destination=DESTINATION, **result), text('MM2_IMPORT_TITLE'))


if __name__ == '__main__':
    main()
