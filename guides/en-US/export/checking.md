# Checking a city

## Validation

**File → Validate city** runs the exporter without keeping its files, and lists what it reports. It is much quicker than testing in the game, so use it often.

It checks with these options: **Export prop rules**, **Export PSDL**, **Export INST**, **Export BAI**, **Export PATHSET**, **Export CINFO and AIMAP** and **Export PKG and bound files**. The hudmap is skipped, to save time.

In the **Validation** panel, errors and warnings are listed with their element. Select one to highlight the element, and click **Zoom to element** or **Edit element**. After fixing it, click **Validate again**.

The same panel opens after an export that reported something.

## Errors and warnings

An **error** makes the export fail, but the exporter still goes on as far as it can, so it reports every problem at once. A room that fails is written empty, so that the other rooms keep their number.

A **warning** means the export finished, but something may not work in the game. Read them all, because many describe a limit of the game.

## Common messages

| Message | What to do |
|---|---|
| A room is not exported, with a perimeter error | Check that element and the connections around it |
| Rooms with props use a high texture index | Reduce the textures, or the rooms with prop rules |
| More than 511 texture references | Reuse textures. See [Limits](../advanced/limits.md) |
| More than 597 different objects in the INST file | Export fewer elements to PKG, and reuse meshes |
| Extra lanes dropped | Use at most 4 lanes per side |
| A cable car line without ends | Leave it open, or add a dead end |
| Decal points outside of the rooms | Move them onto a room |
| An opponent waypoint is not on an intersection, or no single road joins two waypoints | Put a waypoint on every intersection of the route. See [Races](../beginner/races.md) |
| An opponent turns back at a waypoint, or the next road starts behind it | Route it through another intersection, so that it doesn't make a U-turn or a hairpin turn. See [Races](../beginner/races.md) |
| On a circuit, the last waypoint before the finish is not on the intersection of the first waypoint | End the lap on the intersection of the first waypoint, with a waypoint before the finish. See [Races](../beginner/races.md) |
| Parked cars on a slope above 5 degrees | Move them to flatter ground |
| More than 192 paths | Use fewer prop lines, or parked car rows |
| `materials.csv` not found | Import the game assets, which include it |
| Pillow is missing | Install the requirements of the core |

## Check tools

The folder `exporters/psdl/tools` of the core has some tools for exported files, which also work on stock files. Run them with Python:

| Tool | What it checks |
|---|---|
| `psdl_check.py --verbose <file.psdl>` | Room edges that lead to no room, and the texture indices of rooms with prop rules |
| `bai_check.py --lint <file.bai>` | The traffic file, including the roads per intersection |
| `decal_check.py <decals.pathset>` | The faces, tiles and names of the decals |

They need loose files, so unpack an archive first, or export with the **PSDL** file type.

## In the game

When the checks are clean, test in the game. If something goes wrong, look at `mm2.log` in the folder of the game. [Limits and crashes](../advanced/limits.md) lists what its messages mean.
