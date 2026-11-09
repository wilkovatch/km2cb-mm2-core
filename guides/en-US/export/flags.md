# Export options

## What each option writes

| Option | Default | Writes |
|---|---|---|
| **Export prop rules** | On | `propdefs.csv`, `proprules.csv` |
| **Export PSDL** | On | `<city>.psdl`, generated low LOD textures |
| **Export INST** | On | `<city>.inst` |
| **Export BAI** | On | `<city>.bai` |
| **Export CPVS** | On | `<city>.cpvs` |
| **Export PATHSET** | On | Props, decals, race props, trains, boats, bridges (with their generated models), parked cars |
| **Export CINFO and AIMAP** | On | `.cinfo`, `.aimap`, `.sky` and race files |
| **Export hudmap and race maps** | On | Hudmap files, menu images, previews |
| **Export PKG and bound files** | On | Meshes and collisions of **Export to PKG** elements |

## Options that change the result

| Option | Default | What it does |
|---|---|---|
| **Split non coplanar roads** | Off | Splits the sections of roads that aren't flat into two triangles |
| **Accurate BAI culling** | Off | Uses an exact but slower distance check, instead of an approximate one, for the culling data of the BAI file |
| **Accurate CPVS** | Off | Computes the CPVS from more places in each room and higher up: fewer rooms appear late, but the game draws more of them, and it takes several times longer (minutes in a large city) |
| **Cap PSDL materials to 511 (TESTING ONLY)** | Off | Caps the texture indices at 511, which breaks the textures above it. Use it only for testing |
| **Verbose** | Off | Writes more detail to the export log |
| **Pack to .ar archive** | Off | Set by choosing the **MM2 archive (.ar)** file type |

## Linked options

Some options depend on others, and turn read-only when they don't apply:

- **Split non coplanar roads** and **Cap PSDL materials to 511 (TESTING ONLY)** need **Export PSDL**.
- **Accurate BAI culling** needs **Export BAI**.
- **Accurate CPVS** needs **Export CPVS**.

## Exporting less

In a loose export, exporting only what changed is quicker, and the files you skip aren't touched. For example:

- **Only the traffic changed:** keep only **Export BAI** on.
- **The meshes didn't change:** turn off **Export PKG and bound files**. The INST entries and the empty rooms are still written.
- **The map doesn't need updating:** turn off **Export hudmap and race maps**, which can take a while.

Keep in mind that the files of different exports need to match, since they all describe the same city: after changing roads or rooms, export the PSDL and the files that depend on it together. The CPVS depends on the rooms too, and on the buildings and objects in them.

Requirements: **Export hudmap and race maps** needs the Python module Pillow. Without it, the export warns and skips the maps.
