# Blocks in depth

The city geometry of MM2 is the PSDL file, which divides the city into **blocks** (also called rooms). This guide follows on from the [Beginner guide](../beginner/before-you-start.md), and this chapter explains the rules behind most of its advice.

## What becomes a block

| Element | Block |
|---|---|
| Road | One block |
| Intersection | One block, unless it is seamless |
| Terrain patch | One block, or a shared one if merged |
| Building line, mesh | None: they go in the block they stand on |

## Doors between blocks

The game treats each edge of a block as a door to the block on the other side. A car moves from block to block through these doors. An edge that leads to no block leads out of the city, and that is what causes `PHYS.DeclareMover : mover not even in city` in `mm2.log`.

So, inside the city:

- Neighboring blocks have to share their vertices. An edge that only looks connected isn't.
- Each building line should stay on one border between two blocks.

The exporter removes the thin spikes that can form in a perimeter, for example at sidewalk corners where roads meet at a right angle. To check a file yourself, see [Checking a city](../export/checking.md).

## Choosing the block

- **Merge with other connected patches** on a terrain patch shares a block with the connected patches that also have it set.
- **Block number** overrides the automatic choice, when it is greater than 0. Be careful using it together with railings.
- **Perimeter-only block** makes a patch part of a block's perimeter, with nothing drawn.

## Blocks on top of each other

**Add warp** is for blocks that lie on top of another one, such as a bridge over a road. It is available on roads, intersections and terrain patches.

## Seamless intersections

A seamless intersection has no surface, so it doesn't become a block. For the traffic:

- If both roads have the same section and lanes, they become a single road through both blocks.
- Otherwise the joint is a two-road intersection using the block of one of the roads, where vehicles never stop.

The export log warns, and writes no traffic road, for a road that ends on a seamless intersection that can't be made this way, and for roads joined only by seamless intersections in a loop.

## Road sections

Every section of a road must be flat, because its collision is made of flat four-sided pieces. **Make coplanar** rearranges the vertices of roads that bend both horizontally and vertically, and is on by default. The export option **Split non coplanar roads** deals with the sections that are still not flat.

## Rendering order

INST meshes keep their order in the file, and you can rename them to reorder them. This can affect how they draw through transparent objects.
