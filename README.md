This core for [km2 City Builder](https://github.com/wilkovatch/km2-city-builder) adds support for Midtown Madness 2 cities.

> [!NOTE]
> Claude Code and other AI agents were used during the development of this project and for writing its documentation, including this README, and the in-app guides.

## Installing

Install the core from **Settings → Preferences → Cores** of the city builder. The core manager installs and updates it to its tagged releases, and **Show info** lists the changes of each release.

## Guides

The core includes a beginner guide, an advanced guide and an export guide, in **Help > Guides** of the city builder (the files are in `guides`). They explain how to build a city, the MM2 features and limits, and every export option and exported file.

## Game files

No original game data is included with the core. Open or create a city using this core and choose **Scripts → Import MM2 game assets...**, then select the folder of your own MM2 installation (the one containing `MM2CORE.AR` and `MM2TEX.AR`). The stock meshes, textures, prop tuning and `city/materials.csv` are extracted to the builder's `Files/common/MidtownMadness2` folder, where the city templates look for them. The SF and London templates include building presets based on the facades of the stock cities, which need these textures.

## Features

- Roads, intersections and terrain patches exported as PSDL rooms, with railings, prop rules, low LOD road textures and optional export as PKG meshes with their bounds
- Ambient traffic paths (BAI), with lanes, parking, cable car lines and direction arrows in the editor
- Individual props, prop lines, prop polygons, INST meshes and parked cars
- Decals (spline and single), as in `decals.pathset`
- Trains, boats, ducks, ferries and movable bridges
- Races (checkpoints, police cars, opponents and race props for each difficulty)
- HUD map and race menu maps, with map labels
- Optional MM2Hook features (**Assume using MM2Hook** in the Info tab of the city properties)

## Exporting

Select the PSDL format when exporting. The exporter writes PSDL, INST, BAI, PATHSET (props, decals, parked cars, trains, boats, bridges), prop rules, PKG and bounds, CINFO and AIMAP (races, opponents, police, ambient traffic), HUD and race maps, laid out as in the game folder. Choose "MM2 archive (.ar)" to get a single archive to put in the game folder.

`exporters/psdl/tools` contains checkers for exported or stock files: `psdl_check.py` (room perimeters), `bai_check.py` (AI paths) and `decal_check.py` (decals).

Additional texture formats supported: `.tex`. Additional mesh formats supported: `.pkg`.

## Third-party software

- The Python packages used by this core (`pythonInfo/requirements.txt`) are installed with pip from PyPI, their licenses are in `pythonInfo/licenses.txt`.
- The hudmap and race maps are drawn with Pillow, which uses the FreeType library to render the map labels. Portions of this software are copyright © The FreeType Project (https://freetype.org). All rights reserved.
- The bundled Liberation Sans font and generated KM2 Map Labels outline data are licensed under the [SIL Open Font License 1.1](fonts/LICENSE), see [font source and license](fonts/README.md).
