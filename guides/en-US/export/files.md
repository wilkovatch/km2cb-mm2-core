# The exported files

## City geometry and objects

**`city/<city>.psdl`** is the city itself: the blocks with their roads, intersections, terrain, facades, roofs and railings. Its texture list comes from what you used.

**`city/<city>.inst`** lists the static meshes (INST meshes, and elements exported to PKG), each in the block it stands on.

**`geometry/<city>_mesh<n>.pkg`** and **`bound/<city>_mesh<n>_BOUND.*`** are the meshes and collisions of the elements with **Export to PKG** checked. The ground type of the collisions comes from `city/materials.csv`, as explained in [Export to PKG](../advanced/export-to-pkg.md).

## Traffic

**`city/<city>.bai`** holds the paths of the ambient traffic and pedestrians, the road rules and the cable cars. Without it, the game has no traffic and puts the player's car at the origin of the city.

## Props and things along paths

**`city/<city>/props.pathset`** has the individual props, and the native paths of **Pathset line** prop lines.

**`city/<city>/decals.pathset`** has the decals.

**`city/<city>/propdefs.csv`** and **`proprules.csv`** are the prop rules of the game, from **PSDL prop rule** on the left and right sides of roads.

**`race/<city>/`** holds the rest:

| File | What it holds |
|---|---|
| `<race-id>.pathset` | The props that belong to one race |
| `<city>_train.pathset` | Trains |
| `<city>_sailboat.pathset` | Boats, ducks, tugs and water taxis |
| `<city>_ferry.pathset` | The car ferry |
| `<city>_parkedcar.pathset` | Parked cars |
| `<city>_parkedcar_<race>.pathset` | The parked cars of one race, read instead of the main file |

## City settings and races

**`tune/<city>.cinfo`** tells the game the city exists: its name and its races.

**`city/<city>.aimap`** and **`race/<city>/roam.aimap`** hold the settings of the traffic and pedestrians, and those of free roaming.

Each race has these files in **`race/<city>/`**:

| File | What it holds |
|---|---|
| `<race>.aimap`, `<race>.aimap_p` | The settings of the amateur and professional setups |
| `<race>waypoints.csv` | Its checkpoints |
| `<opponent>.opp` | The route of each opponent |
| `mm<racetype>data.csv` | The list of races of that type |

## Maps

**`texture/<city>_hudmap<n>.tex`** and **`_ni.tex`** are the tiles of the map of the HUD, for the day and the night.

**`geometry/hudmap_<city>.pkg`** places those tiles in the city.

**`tune/<city>.mmHudMap`** holds the size and zoom of the map, and the color around it.

**`jpg/<city>_maproam.jpg`** and **`jpg/<city>_map<race>.jpg`** are the images of the menus.

## The intermediate file

**`city/<city>.bin`** is the exporter's own format, used between reading the city and writing the game files. It is deleted after a normal export, and kept only with **Export BIN only**. The game doesn't use it.

## What isn't exported

- The textures and meshes of your city, in a loose export. See [Where the files go](layout.md).
- The stock textures and meshes, which the game already has. Any texture a decal uses must be in the game.
