# Export to PKG

Check **Export to PKG** on a road, intersection, terrain patch or building line to export it as a mesh instead of PSDL geometry. It saves PSDL vertices, and allows shapes that the PSDL can't have.

## What happens

- Roads, intersections and terrain patches still become rooms, but empty ones, with the perimeter of the element and no surface. The element is placed in its room through the INST file.
- Building lines are placed in the room they are on, as usual.
- The meshes go in `geometry/<city>_mesh<n>.pkg`, with only the low level of detail, which the game uses at every distance.
- Their collisions go in `bound/<city>_mesh<n>_BOUND.bnd`, `.bbnd` and `.ter`.

## Ground types

The material of a collision, such as cobblestone or grass, comes from the textures of its polygons, through the file `city/materials.csv` of the game.

Importing the game assets copies this file to `Files/common/MidtownMadness2/city/materials.csv`. If you use custom textures, add them to this copy and to the one in the game. Textures not listed, or a missing file, use the `default` material.

## The cost

> Each element exported to PKG is a different object for the game, and the game can load only about 600 different objects. Don't use it on every building line.

Other limits:

- A collision can have at most 65535 vertices and polygons.
- The TER file can have at most 65535 polygon references, in cells of about 10 m.

Bigger ones are skipped, with a warning.

## Saving time

When the meshes haven't changed, uncheck **Export PKG and bound files** in the export dialog. The exporter then writes only the INST entries and the empty rooms.
