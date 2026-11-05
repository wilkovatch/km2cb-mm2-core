# Terrain

The grid isn't part of your city in the game. Only terrain patches, roads and intersections make the surface that cars drive on.

The simplest way is **Create → Whole city terrain**, once the roads are finished. It is also the safest, because the patches connect to the roads exactly.

## Why blocks matter here

Each terrain patch becomes a block of its own, unless patches are merged. Blocks must be connected **point by point**, so that the game can move from one to the next:

- Attach the points of a hand-made patch to the green anchors of the roads next to it.
- Avoid a patch edge that runs along a road without sharing its points.

If a car crosses a gap between blocks, the game loses track of it. In `mm2.log` this shows as `mover not even in city`.

## Merging patches

**Merge with other connected patches** puts connected patches into the same block. It is on by default for patches placed by hand, and off for automatically placed ones. Two patches count as connected when they share at least one edge.

> Railings can only sit on the perimeter of a block, so be careful when you merge patches that have railings.

## Invisible patches

A patch with no texture is invisible, but it still creates an **empty block**. Empty blocks are useful: they can contain meshes, buildings and other things.

This matters because things that need a block have to be on one. An INST mesh that is not on anything that becomes a block is not exported.

## Surfaces

The texture of a patch also decides the surface in the game: asphalt, grass, water and so on, through the `city/materials.csv` file of the game. If you use your own textures, add them to that list. The [Export guide](../export/files.md) has the details.
