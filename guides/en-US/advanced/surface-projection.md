# Surface projection

In MM2 the grid is only a placement guide, so what you see on it isn't necessarily what's in the game.

## What things stand on

**Elements that project onto city surfaces**, such as decals, look for these first:

- Roads
- Intersections
- Terrain patches
- Supported custom geometry
- INST meshes

They use the grid only if they find none of these, even when the surface is several meters below the grid. Props are not targets for this.

**Roads and other elements that follow the heightmap** keep following it.

## Following changes

Projected strips follow edits to INST meshes, including moving, replacing, deleting and undo. The saved control points keep their placement.

## Heights in the game

The game doesn't look for the ground when it places some things, so what you see in the editor matters:

- **Parked cars** are at the height of their path.
- **Pathset lines** with **Project to ground** have a point on the path for each prop, so that they follow the ground.
- **Trains and boats** keep the height of their points exactly.
- **Parked car** single slots keep their height until you use **Project to ground** again.

## Working under the grid

**View → Hide terrain grid** hides the grid, which can't be clicked while it is hidden. Use it to place things on a surface the grid covers. The full manual, in **Help → Quickstart guide**, explains how this affects projection.
