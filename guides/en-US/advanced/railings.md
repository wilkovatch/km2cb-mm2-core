# Railings

Railings, walls and galleries can go on roads and on terrain patches.

## On roads

Go to the **Railing** tab of the road and set the properties. The options are **Railing**, **Wall**, **Flat gallery** and **Curved gallery**, each with its own textures.

The **Continue** checkboxes at the bottom of the tab say whether the railing goes on across each neighboring intersection, separately for the left and right side at each end.

## On terrain patches

1. Go to the **Railing** tab of the patch and click **Add railing**.
2. Set its properties.
3. Click **Switch to railing placement**.
4. Click the perimeter points of the patch where the railing goes.

> Railings are placed on the perimeter of the **block**, not of the terrain patch. Select points that are also perimeter points of the block, or it won't work properly in the game.

This matters most with **Merge with other connected patches**, since merged patches share a single block, and points between them aren't on its perimeter.

A railing can't start at vertex 0 of a perimeter when the perimeter can't be rotated: the export log warns about this.
