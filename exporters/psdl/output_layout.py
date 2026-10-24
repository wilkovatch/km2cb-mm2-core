import os
from pathlib import Path


class OutputLayout:
    # The files are written as in the game folder: the PSDL goes in a "city" folder (the one of the chosen file
    # if it is named so, otherwise one created in the chosen folder), the others in the folders next to it
    # (tune, race/<city>, geometry, bound, texture, jpg)
    def __init__(self, chosen_psdl):
        chosen = os.path.abspath(chosen_psdl)
        folder = os.path.dirname(chosen)
        self.city_name = Path(chosen).stem
        if os.path.basename(folder).lower() == 'city':
            self.root = os.path.dirname(folder)
            self.psdl = chosen
        else:
            self.root = folder
            self.psdl = os.path.join(folder, 'city', os.path.basename(chosen))

    def path(self, name):
        # the path of a folder of the layout (not created)
        if name == 'city':
            return os.path.dirname(self.psdl)
        if name == 'race':
            return os.path.join(self.root, 'race', self.city_name)
        return os.path.join(self.root, name)

    def dir(self, name):
        # the path of a folder of the layout, created if missing, with the trailing separator
        path = self.path(name)
        if not os.path.exists(path):
            os.makedirs(path)
        return path + os.sep
