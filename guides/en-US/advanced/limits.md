# Limits and crashes

## Limits of the game

| Limit | Value | What the exporter does |
|---|---|---|
| Lanes per side of a road | 4 | Drops the extra lanes, warns |
| Roads at a traffic intersection | 11 | Splits the intersection, warns |
| Different textures in the city | 511 in stock MM2 | Warns (see below) |
| Texture index of a room with prop rules | Below 255 | Reorders them, or drops the props and warns |
| Different INST objects | About 600 | Warns above 597 |
| PSDL vertices | 65536 | |
| Paths in a pathset file | 192 | Reports an error, writes the first 192 |
| Texture names in decals | 31 characters | |
| Vertices or polygons of a PKG collision | 65535 | Skips it, warns |

The objects limit is shared: the meshes of the INST file, the props and the vehicles share about 4096 slots, and each different object in the INST file takes 6. Instances of the same mesh count once, but each element exported to PKG is a different object.

## Too many textures

Stock MM2, and tools such as MM2 City Toolkit, can't handle PSDL files with more than 511 texture references. Above that, the exporter warns, and the wording of the warning depends on **Assume using MM2Hook**.

The export option **Cap PSDL materials to 511 (TESTING ONLY)** caps the indices, which breaks the textures above the limit. Use it only for testing. Without it, there is still a cap of 2047.

Reuse textures. Generated low LOD textures count too: one for each different road.

## Reading mm2.log

`mm2.log` is in the folder of the game. If you use MM2Hook, also look at `mm2hook.log`.

| Message | Meaning | What to do |
|---|---|---|
| `PHYS.DeclareMover : mover not even in city` | A car is outside of every room | Look for gaps, and for edges not connected to a neighboring room |
| `Vehicle ... did not have permission to traverse intersection` | The **First in, first out** rule was broken | Try another rule at that intersection |
| Exception at `0045da58` after "Placing props along road segments" (or "Invalid command" without the hook) | A room with a prop rule uses a texture index of 255 or more | Reduce the textures, or the rooms with prop rules |
| Exception at `004a48d8` after "Loading objects...", then `memMemoryAllocator::FindHeap failed` | Too many different objects | Export fewer elements to PKG, reuse meshes |
| A crash in the ambient traffic (around `0053a0d2`) | An intersection with more than 11 roads | Reduce the roads there |
| A crash at `005440c5`, in the update of lane vehicles | The cause isn't known yet | |

## If the player starts somewhere strange

Without a BAI file, the game puts the player's car at the origin of the city, so the city is unplayable if nothing is there. Make sure something is at the origin, or export the BAI file.
