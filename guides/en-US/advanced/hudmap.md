# Hudmap in depth

The maps are drawn from the geometry of the city, seen from above with north (-Z in the game) at the top. They need the Python module Pillow, which is installed with the requirements of the core.

## The map of the HUD

- It is made of tiles of 256 or 512 pixels, at 5.5 m per pixel like the stock maps.
- The tiles go in `texture/<city>_hudmap<n>.tex`, with a `_ni` copy for the night.
- `geometry/hudmap_<city>.pkg` places them in the city.
- `tune/<city>.mmHudMap` holds the size and zoom of the map and the color around it.

Keep the map within 16 tiles, by changing **Meters per pixel** or **Tile size**. Empty tiles are left out, as are tiles with only water when its color matches the background.

## Race maps

These are the images of the race menus, 242x184 pixels with the frame of the menu:

- `jpg/<city>_maproam.jpg` shows the whole city.
- `jpg/<city>_map<race>.jpg` shows the area of the checkpoints of each race, with the start in red and the checkpoints in green.

The frame is a plain color. To use a stock frame, copy a stock map image to `Files/common/MidtownMadness2/jpg/mapframe.jpg`.

## Colors and categories

**Background** sets the color of uncovered areas on all the maps, and around the map of the HUD, as `#RRGGBB`. If you leave it empty, it uses the **Water** color, which also sets the color of water surfaces.

What each element draws as:

| Element | Default |
|---|---|
| Roads, intersections | Road, or grass or water by their texture |
| Terrain patches | Ground, or grass or water by their texture |
| Perimeter-only patches | Not drawn |
| Roofs of building lines | Buildings |
| Mesh instances | Not drawn |

Grass and water come from the physics material of the texture in `city/materials.csv` (grass, mud, water, deepwater), or from its name (grass, park, lawn, water, pond, river, sea).

**Hudmap category** overrides this on any of these elements. For example, use **Landmark** to draw a building in red, **Ground** for a walkway inside a block, or **Hidden**. A mesh instance with a category is drawn as its bounding box. The parts of roads passing through an intersection take the category of the intersection, unless they have their own.

## Labels

Opening the **Hudmap** tab, its list of labels or a label selects the Hudmap container, and all labels appear in the city. They stay visible until you deselect the container from the blue menu, or switch to another tab of the city properties.

- **Size** is in pixels of the race maps, 6.75 by default. Labels on the roam map are 75% of this.
- **Shown on** chooses between all the maps, the roam map and the race maps.
- **Label font** sets a custom `.ttf` or `.otf` font for the exported maps. The default is the bundled Liberation Sans Bold, which is similar to the stock style.
- The **Labels** color affects only the exported maps.

On the map, names are small uppercase bold letters with wide spacing, in translucent black. The race start and checkpoints are drawn over them.

Latin accents are supported in the editor preview. Other characters show as a box there, but keep their full text in the export.
