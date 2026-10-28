"""Selective stock MM2 DAVE extraction. Only the standard library is needed.

Format reference: https://github.com/EdnessP/scripts/blob/main/midnight-club/dave.py
The original MM2 archives use DAVE (ASCII filenames), not Dave (compressed filenames) or ZIP.
"""
from contextlib import ExitStack
from dataclasses import dataclass
import os
from pathlib import Path
import struct
import tempfile
import time
import zlib


class ImportFailure(Exception):
    def __init__(self, key, **values):
        super().__init__(key)
        self.key = key
        self.values = values


@dataclass(frozen=True)
class Entry:
    name: str
    offset: int
    size: int
    stored_size: int


def safe_name(name, archive):
    name = name.replace('\\', '/')
    parts = name.split('/')
    # Trailing / marks a directory; explicit directory records are not imported.
    if parts[-1] == '':
        parts.pop()
    if not parts or any(not part or part in ('.', '..') or any(c in '<>:"|?*' for c in part) or
                        part.endswith((' ', '.')) or any(ord(c) < 32 for c in part) for part in parts):
        raise ImportFailure('MM2_IMPORT_UNSAFE_PATH', archive=str(archive), entry=name)
    return '/'.join(parts).lower()


class DaveArchive:
    def __init__(self, path):
        self.path = Path(path)
        self.file = None
        self.entries = []

    def fail(self, key, **values):
        raise ImportFailure(key, archive=str(self.path), **values)

    def __enter__(self):
        self.file = self.path.open('rb')
        try:
            self._read_index()
        except BaseException:
            self.file.close()
            raise
        return self

    def __exit__(self, *args):
        self.file.close()

    def _read_index(self):
        length = os.fstat(self.file.fileno()).st_size
        header = self.file.read(16)
        if len(header) < 4:
            self.fail('MM2_IMPORT_INDEX')
        if header[:4] != b'DAVE':
            self.fail('MM2_IMPORT_SIGNATURE', signature=repr(header[:4]))
        if len(header) != 16:
            self.fail('MM2_IMPORT_INDEX')
        _, count, index_size, names_size = struct.unpack('<4sIII', header)
        names_start = 0x800 + index_size
        data_start = names_start + names_size
        if count == 0 or count * 16 > index_size or data_start > length:
            self.fail('MM2_IMPORT_INDEX')
        self.file.seek(0x800)
        index = self.file.read(count * 16)
        self.file.seek(names_start)
        names = self.file.read(names_size)
        if len(index) != count * 16 or len(names) != names_size:
            self.fail('MM2_IMPORT_INDEX')
        for i, (name_offset, offset, size, stored_size) in enumerate(struct.iter_unpack('<4I', index)):
            end = names.find(b'\0', name_offset)
            if name_offset >= names_size or end < 0:
                self.fail('MM2_IMPORT_NAME', index=i)
            try:
                original_name = names[name_offset:end].decode('ascii')
            except UnicodeDecodeError:
                self.fail('MM2_IMPORT_NAME', index=i)
            name = safe_name(original_name, self.path)
            if offset < data_start or offset + stored_size > length or (size > 0 and stored_size == 0):
                self.fail('MM2_IMPORT_PAYLOAD', entry=name)
            if not original_name.endswith(('/', '\\')):
                self.entries.append(Entry(name, offset, size, stored_size))

    def read(self, entry):
        self.file.seek(entry.offset)
        data = self.file.read(entry.stored_size)
        if len(data) != entry.stored_size:
            self.fail('MM2_IMPORT_PAYLOAD', entry=entry.name)
        if entry.size != entry.stored_size:
            try:
                decoder = zlib.decompressobj(-15)
                # Bound the output by the declared size, including one byte to detect overflow.
                data = decoder.decompress(data, entry.size + 1)
                if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                    self.fail('MM2_IMPORT_DECOMPRESSION', entry=entry.name)
            except zlib.error:
                self.fail('MM2_IMPORT_DECOMPRESSION', entry=entry.name)
        if len(data) != entry.size:
            self.fail('MM2_IMPORT_DECOMPRESSION', entry=entry.name)
        return data


def selected(name, archive):
    if archive == 'mm2core.ar':
        return (name == 'city/materials.csv' or
                (name.startswith('geometry/') and name.endswith(('.pkg', '.mtx'))) or
                (name.startswith('tune/banger/') and name.endswith('.dgbangerdata')))
    return name.startswith('texture/') and name.endswith(('.tex', '.tga'))


def directory_entries(folder):
    entries = {}
    for path in folder.iterdir():
        key = path.name.casefold()
        if key in entries:
            raise ImportFailure('MM2_IMPORT_AMBIGUOUS', path=str(path))
        entries[key] = path
    return entries


class Destination:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.cache = {}

    def target(self, entry, archive):
        folder = self.root
        parts = entry.split('/')
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            if folder not in self.cache:
                folder.mkdir(parents=True, exist_ok=True)
                self.cache[folder] = directory_entries(folder)
            children = self.cache[folder]
            path = children.get(part.casefold(), folder / part)
            # Reject symlinks (even broken ones), junctions leading outside, and file/directory collisions.
            resolved = path.resolve()
            if (path.is_symlink() or not resolved.is_relative_to(self.root) or
                    (path.exists() and not (path.is_file() if last else path.is_dir()))):
                raise ImportFailure('MM2_IMPORT_DESTINATION', archive=archive, entry=entry, destination=str(self.root))
            if last:
                return path
            path.mkdir(exist_ok=True)
            children[part.casefold()] = path
            folder = path

    def remember(self, path):
        self.cache[path.parent][path.name.casefold()] = path


def write_atomic(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.km2-mm2-import-', suffix='.tmp', dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def import_assets(game_folder, destination, overwrite=False, progress=None):
    archive_name = ''
    entry_name = ''
    try:
        if not str(game_folder).strip():
            raise ImportFailure('MM2_IMPORT_FOLDER_REQUIRED')
        source = Path(game_folder).expanduser()
        if not source.is_dir():
            raise ImportFailure('MM2_IMPORT_FOLDER_MISSING', folder=str(source))
        sources = directory_entries(source)
        paths = []
        for name in ('mm2core.ar', 'mm2tex.ar'):
            archive_name = name
            path = sources.get(name)
            if path is None or not path.is_file():
                raise ImportFailure('MM2_IMPORT_ARCHIVE_MISSING', archive=name.upper(), folder=str(source))
            paths.append(path)

        with ExitStack() as stack:
            planned = []
            seen = set()
            # Validate both indexes and all selected names before creating the destination.
            for path in paths:
                archive_name = str(path)
                archive = stack.enter_context(DaveArchive(path))
                entries = [e for e in archive.entries if selected(e.name, path.name.lower())]
                if not entries:
                    raise ImportFailure('MM2_IMPORT_NO_ASSETS', archive=archive_name)
                for entry in entries:
                    if entry.name.casefold() in seen:
                        raise ImportFailure('MM2_IMPORT_DUPLICATE', archive=archive_name, entry=entry.name)
                    seen.add(entry.name.casefold())
                    planned.append((archive, entry))
            output = Destination(destination)
            result = dict(imported=0, replaced=0, skipped=0, bytes_written=0)
            last_progress = -float('inf')
            for done, (archive, entry) in enumerate(planned, 1):
                archive_name, entry_name = str(archive.path), entry.name
                path = output.target(entry.name, archive_name)
                existed = path.exists()
                if existed and not overwrite:
                    result['skipped'] += 1
                else:
                    data = archive.read(entry)
                    write_atomic(path, data)
                    output.remember(path)
                    result['replaced' if existed else 'imported'] += 1
                    result['bytes_written'] += len(data)
                now = time.monotonic()
                if progress is not None and (now - last_progress >= 0.1 or done == len(planned)):
                    progress(done, len(planned), archive.path.name, entry.name)
                    last_progress = now
            return result
    except OSError as error:
        raise ImportFailure('MM2_IMPORT_IO', archive=archive_name, entry=entry_name, detail=str(error)) from error
