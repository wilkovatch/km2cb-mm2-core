# Export options

## What each option writes

| Option | Default | Writes |
|---|---|---|
| **Export prop rules** | On | `propdefs.csv`, `proprules.csv` |
| **Export BIN only** | Off | Only the `.bin` file (see below) |
| **Export PSDL** | On | `<city>.psdl` |
| **Export INST** | On | `<city>.inst` |
| **Export BAI** | On | `<city>.bai` |
| **Export PATHSET** | On | Props, decals, race props, trains, boats, parked cars |
| **Export CINFO and AIMAP** | On | `.cinfo`, `.aimap` and race files |
| **Export hudmap and race maps** | On | Hudmap files, menu images, previews |
| **Export PKG and bound files** | On | Meshes and collisions of **Export to PKG** elements |

## Options that change the result

| Option | Default | What it does |
|---|---|---|
| **Split non coplanar roads** | Off | Splits the sections of roads that aren't flat into two triangles |
| **Accurate BAI culling** | Off | Uses an exact but slower distance check, instead of an approximate one, for the culling data of the BAI file |
| **Cap PSDL materials to 511 (TESTING ONLY)** | Off | Caps the texture indices at 511, which breaks the textures above it. Use it only for testing |
| **Verbose** | Off | Writes more detail to the export log |
| **Pack to .ar archive** | Off | Set by choosing the **MM2 archive (.ar)** file type |

## Linked options

Some options depend on others, and turn read-only when they don't apply:

- **Split non coplanar roads** and **Cap PSDL materials to 511 (TESTING ONLY)** need **Export PSDL**.
- **Accurate BAI culling** needs **Export BAI**.
- **Export BIN only** makes **Export PSDL**, **Export INST**, **Export BAI**, **Export PATHSET**, **Export PKG and bound files** and the options that depend on them read-only, and they are not written.
- **Pack to .ar archive** makes **Export BIN only** read-only.

## Export BIN only

This option writes `city/<city>.bin` and keeps it, for inspection and tools. **It doesn't turn off everything:** **Export prop rules**, **Export CINFO and AIMAP** and **Export hudmap and race maps** keep their own checkboxes, so turn them off too if you want only the BIN file.

## Exporting less

In a loose export, exporting only what changed is quicker, and the files you skip aren't touched. For example:

- **Only the traffic changed:** keep only **Export BAI** on.
- **The meshes didn't change:** turn off **Export PKG and bound files**. The INST entries and the empty blocks are still written.
- **The map doesn't need updating:** turn off **Export hudmap and race maps**, which can take a while.

Keep in mind that the files of different exports need to match, since they all describe the same city: after changing roads or blocks, export the PSDL and the files that depend on it together.

Requirements: **Export hudmap and race maps** needs the Python module Pillow. Without it, the export warns and skips the maps.
