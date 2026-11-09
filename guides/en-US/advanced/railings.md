# Railings

Railings, walls and galleries can go on roads, and along the edges of any room with a **Rail** element.

## On roads

Go to the **Railing** tab of the road and set the properties. The options are **Railing**, **Wall**, **Flat gallery** and **Curved gallery**, each with its own textures.

The **Continue** checkboxes at the bottom of the tab say whether the railing goes on across each neighboring intersection, separately for the left and right side at each end.

Pieces of road drawn through an intersection have no railings, as in the editor.

## Along the edges of a room

A **Rail** puts a railing or a wall on edges of a room: the perimeter of a terrain patch, or the sides of a road or intersection.

1. Choose **Create > Rail (room perimeter)** and set the type (**Railing** or **Wall**), the height and the textures.
2. Click a perimeter point of a terrain patch, or a point on the side of a road or intersection. Only these points are shown. This chooses the **Room** of the rail. When the point is on two of them (a patch point on the side of a road), a menu asks which one.
3. Click the point where the rail ends. Only the points of its room are shown now. The rail follows the perimeter of its room between the two points, the shorter way. To go the other way around, click a point on that side before the last one.
4. Click the first point again to go all around (or tick **Loop**).

The rail keeps following the perimeter when you add, move or remove its points between the ones you clicked. The arrows show its direction: a rail goes clockwise around its room, seen from above, and is drawn on the outside (**Reverse** puts it on the other side).

> Railings are flags on the edges of the **room**. An edge that isn't on the perimeter of its room (for example between two patches merged into one room) can't have a railing: the export log says how many edges of a rail were left out.

A rail stays in one room: for the edges of another room, make another rail.

A railing can't start at vertex 0 of a perimeter when the perimeter can't be rotated: the export log warns about this.
