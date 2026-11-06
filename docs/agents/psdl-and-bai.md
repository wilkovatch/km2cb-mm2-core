# PSDL rooms and BAI

Read the [repository instructions](../../AGENTS.md) first. Paths and command examples below are relative to this repository root unless another working directory is specified. Builder CLI and self-test commands run from the builder root.

Also read [Exporter workflow and engine limits](exporting.md) and [The PSDL exporter](../exporter.md), which describes the parts, the rooms and the BAI model. Stock tram/train facts are in [Trains and boats](trains-and-boats.md#stock-data); texture conventions are in [Decals, textures and maps](decals-textures-and-maps.md#native-texture-reference).

## PSDL attributes as custom elements (removed)

The core had custom element types for the PSDL room attributes, the rooms, groups of building parts and the BAI roads and intersections (`creatable: false`, made by the `toPsdl`, `roomPerimeter` and triangle fan converters), with their exporter support (`custom_elements.py`, the mapping in `custom_element_conversion.py`), Lua (`psdl.lua`) and API self-tests. They were removed on 2026-11-06 with the exporter refactoring, to be redone later: the git history before that date has them. The exporter ignores such elements in older cities (how the builder loads elements of a missing type wasn't checked), and exports the roads and intersections they replaced (ghosts) again.

## BAI and pedestrians

**Paths:** the BAI uses the paths drawn in the editor (traffic lanes, pedestrian paths, cable car rails, see [The PSDL exporter](../exporter.md#the-bai)). The pedestrian paths are on the sidewalk surface, 7.5 cm above the stock convention (the sidewalk centre midway between the curb at road level and the outer edge); the rails follow the side of their lanes (the old derived rails were always on +x, which a few test roads have on the left side).

**Pedestrians (BAI sidewalks):** the walk target is evaluated 6 m ahead on an **unclamped** Hermite curve, so short sidewalk segments that turn make pedestrians fly off and circle. Segments touching a sharp corner need to be ≥ ~16 m. `bai_writer.spread_corner_points` moves only the sidewalk points; the 2 m car sections stay.

**BAI:** coordinates are (x, up, z) with x mirrored. The engine's room lookup returns the first intersection of a room before its roads, so don't put extra intersections in road rooms. For stock BAI derivation rules see the maintainer's psdl-viewer project, `Scripts/Formats/BaiFile.cs` (location in the builder's `CLAUDE.local.md`).
