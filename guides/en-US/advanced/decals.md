# Decals in depth

## How the game draws them

Each decal is a strip with its texture tiled along it, in square tiles as wide as the strip, with a whole number of tiles in each piece.

- **Pieces and blocks:** a decal is divided into pieces, one per segment, at most 25 m long. The game draws each piece only when the block where it starts is visible. So keep decals on the blocks: the export log warns about points outside of them.
- **Height:** decals are lifted by 1 cm, to stay above the surface.
- **Names:** the path of a decal is named after its texture, so texture names can have at most 31 characters.

Decals are exported with the PATHSET, to `city/<city>/decals.pathset`. The tool `exporters/psdl/tools/decal_check.py` checks these files: their faces, tiles and names.

## Spline decals

**Create → Decals → Spline** opens the panel right away, so you can set the texture, width and curve mode before placing any point. Curve modes are low-poly, Bézier and Hermite. New decals placed by hand use Bézier, as the curve type isn't part of a preset.

Points project onto the surface when placed or moved. Presets work as usual, and syncing keeps the points of the linked decals.

## Single decals

A single decal is one piece of the same file:

- It moves on X and Z only, since its height follows the surface, and turns around Y only.
- Scale X is its width and scale Z its length. Presets include the size.
- Only its center is put on the surface, so on a slope the rectangle stays flat.
- A negative scale mirrors it, and it is then not drawn, so the export warns about it.
- Keep it under 25 m, on the blocks.

## Surfaces

Decals look for a surface in this order: roads, intersections, terrain patches, supported custom geometry and INST meshes. They use the grid only if there is no such surface. See [Surface projection](surface-projection.md).
