import os
import zipfile
from common import report


class ArPacker:
    # Packs the exported files, as in the game folder (see output_layout.py), in an .ar archive: a zip file, which
    # the game reads like its own archives. The geometry and texture folders of the city (the custom meshes and
    # textures) are packed too, the exported files override the custom files with the same name
    CITY_FOLDERS = ['geometry', 'texture']

    def __init__(self, layout, city_folder, verbose):
        self.layout = layout
        self.city_folder = city_folder
        self.verbose = verbose

    def is_placeholder(self, name):
        # the files of the city templates that tell what to put in the folder ("_put custom pkg files here")
        return name.startswith('_put ') and name.endswith(' here')

    def add_folder(self, entries, folder, prefix):
        # adds the files of the folder (recursively), named <prefix>/<path in the folder>
        for dirpath, _, filenames in os.walk(folder):
            for filename in filenames:
                if self.is_placeholder(filename):
                    continue
                source = os.path.join(dirpath, filename)
                name = os.path.relpath(source, folder).replace(os.sep, '/')
                if prefix != '':
                    name = prefix + '/' + name
                entries[name.lower()] = (name, source)

    def get_entries(self):
        entries = {}  # lower case name -> (name in the archive, source file)
        if self.city_folder is None or self.city_folder == '' or not os.path.isdir(self.city_folder):
            report.warning("the folder of the city is not known, its geometry and texture folders are not packed")
        else:
            for name in self.CITY_FOLDERS:
                self.add_folder(entries, os.path.join(self.city_folder, name), name)
        # the files in the root are not game files (the hudmap preview)
        for name in sorted(os.listdir(self.layout.root)):
            path = os.path.join(self.layout.root, name)
            if os.path.isdir(path):
                self.add_folder(entries, path, name)
        return entries

    def pack(self, ar_path):
        print("Packing the AR file...")
        entries = self.get_entries()
        # written next to it first, so that an error does not leave a broken archive in place of the previous one
        tmp_path = ar_path + '.tmp'
        try:
            with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as archive:
                for key in sorted(entries):
                    name, source = entries[key]
                    if self.verbose:
                        print("  " + name)
                    archive.write(source, name)
            os.replace(tmp_path, ar_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        print("AR file packed! (" + str(len(entries)) + " files)")
