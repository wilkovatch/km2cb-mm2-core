# PSDL rooms and BAI

Read the [repository instructions](../../AGENTS.md) first. Paths and command examples below are relative to this repository root unless another working directory is specified. Builder CLI and self-test commands run from the builder root.

Also read [Exporter workflow and engine limits](exporting.md) and [The PSDL exporter](../exporter.md), which describes the parts, the rooms and the BAI model. Stock tram/train facts are in [Trains and boats](trains-and-boats.md#stock-data); texture conventions are in [Decals, textures and maps](decals-textures-and-maps.md#native-texture-reference).

## PSDL attributes as custom elements (removed)

The core had custom element types for the PSDL room attributes, the rooms, groups of building parts and the BAI roads and intersections (`creatable: false`, made by the `toPsdl`, `roomPerimeter` and triangle fan converters), with their exporter support (`custom_elements.py`, the mapping in `custom_element_conversion.py`), Lua (`psdl.lua`) and API self-tests. They were removed on 2026-11-06 with the exporter refactoring, to be redone later: the git history before that date has them. The exporter ignores such elements in older cities (how the builder loads elements of a missing type wasn't checked), and exports the roads and intersections they replaced (ghosts) again.

## BAI and pedestrians

**Paths:** the BAI uses the paths drawn in the editor (traffic lanes, pedestrian paths, cable car rails, see [The PSDL exporter](../exporter.md#the-bai)). The pedestrian paths are on the sidewalk surface, 7.5 cm above the stock convention (the sidewalk centre midway between the curb at road level and the outer edge); the rails follow the side of their lanes (the old derived rails were always on +x, which a few test roads have on the left side).

**Pedestrians (BAI sidewalks):** the walk target is evaluated 6 m ahead on an **unclamped** Hermite curve, so short sidewalk segments that turn make pedestrians fly off and circle. Segments touching a sharp corner need to be ≥ ~16 m. `bai_writer.spread_corner_points` moves only the sidewalk points; the 2 m car sections stay.

**BAI:** coordinates are (x, up, z) with x mirrored. The engine's room lookup returns the first intersection of a room before its roads, so don't put extra intersections in road rooms. For stock BAI derivation rules see the maintainer's psdl-viewer project, `Scripts/Formats/BaiFile.cs` (location in the builder's `CLAUDE.local.md`).

**BAI-only roads** (the `bai` road type, `"geometryless": true` in its settings, see the builder's `wiki/Core-Roads.md`): the same `sectionVertices`, traffic components (copies of the `trafficLanes` of `doubleRoad`/`singleRoad`, `dividedRoad` and the sidewalks, without meshes) and traffic parameters as `psdl`, with `hVal` 0 (the lanes and curbs at the height of the curve, where a PSDL road with sidewalks has its road 15 cm lower). `divider` is only none or divided (1, which the BAI sees as a divided road). `get_geometryless_bai_sections` takes `v6, v5, (v4, v2), v1, v0` with sidewalks and `v5, (v4, v2), v1` without them, the order of `get_road_sections_layout` on the mesh of a PSDL road; `exporters/psdl/tools/_test_geometryless_roads.py` checks it against a PSDL twin on the export of the `geometrylessRoads` API focus. Their rooms are the PSDL rooms under them (`resolve_traffic_rooms`), so a network of BAI-only roads over a single terrain patch puts all its intersections in one room, with a warning for each but the first: give each intersection its own room (a small patch under it). Not tested in the game yet.
