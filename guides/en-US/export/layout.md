# Where the files go

The files are written with the same layout as the folder of the game, so you can copy them there as they are.

## The city folder

The PSDL goes in a folder named `city`:

- If the file you chose is already in a folder named `city`, that folder is used.
- Otherwise, a `city` folder is created in the folder you chose.

The other folders are created next to the `city` folder. So if you export into a new empty folder, you get everything in one place, ready to copy.

## The layout

| Folder | Files |
|---|---|
| `city/` | `<city>.psdl`, `<city>.inst`, `<city>.bai`, `<city>.aimap` |
| `city/<city>/` | `props.pathset`, `decals.pathset`, `proprules.csv`, `propdefs.csv` |
| `tune/` | `<city>.cinfo`, `<city>.mmHudMap` |
| `race/<city>/` | `roam.aimap`, the files of each race, and the train, boat and parked car paths |
| `geometry/` | `<city>_mesh<n>.pkg`, `hudmap_<city>.pkg` |
| `bound/` | `<city>_mesh<n>_BOUND.bnd`, `.bbnd` and `.ter` |
| `texture/` | `<city>_hudmap<n>.tex`, `<city>_hudmap<n>_ni.tex` |
| `jpg/` | `<city>_maproam.jpg`, `<city>_map<race>.jpg` |

## Outside of the layout

Two preview images are written next to the folders, and aren't used by the game:

- `<city>_hudmap_preview.png` shows the map of the HUD.
- `<city>_hudmap_labels_preview.png` shows the same map with the roam labels.

## Exporting again

Exporting over an earlier export replaces the files it writes, even with shorter ones. The exporter also removes its own files that are no longer needed, such as the props of a deleted race. To do this, it keeps small `.km2-*` lists of the files it owns. They are left out of archives.

## Custom textures and meshes

A **loose** export doesn't copy the custom textures and meshes of your city. Copy the `texture` and `geometry` folders of the city folder to the game yourself. The archive includes them.
