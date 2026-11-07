# The PSDL exporter

> Claude Code and other AI agents were used during the development of this project and for writing its documentation, including this page.

The exporter of the core (`exporters/psdl`) writes a city as the files of Midtown Madness 2: the PSDL (the city geometry), CPVS (the rooms visible from each room), INST (objects), BAI (the paths of the ambient traffic, the pedestrians and the cable cars), PATHSET (props, decals, parked cars, trains, boats, bridges), prop rules, PKG and bound files, CINFO and AIMAP files, the hudmap and the race maps. They're written as in the game folder (`output_layout.py`), or packed in an `.ar` archive. The flags and the files are described for users in the export guide (`guides/en-US/export`). This page describes how the exporter works, for those changing it. The facts about the game (formats, limits, crashes) are in the agent notes, [Exporter workflow and engine limits](agents/exporting.md) and the topics it links.

The program runs the exporter as described in the builder's wiki (Core Python Integration): it writes the export JSON of the city and runs `export.py` with the bundled Python.

## Pipeline

```
export JSON ──► JsonProcessor ──► parts (ExportedCityElement, program space)
                    │                   │
                    │                   ▼
                    │               Scene (writer space) ──► PSDL, CPVS, INST, PATHSET, decals, PKG/bounds
                    ▼                   │ (rooms)
             BaiNetworkBuilder ──► BaiNetwork ──────────────► BAI
                    │
                    └──► hudmap arrows
JSON only ──► prop rules, trains, boats, bridges, parked cars, CINFO/AIMAP, hudmap, race maps
```

1. `export.py` reads the arguments (`options.py`), decodes the JSON and checks the race ownership (`race_elements.validate_ownership`), then writes the generated files (`generated_export.py`: low LOD textures under `psdl`, bridge models under `pathset`) and puts their paths in the data.
2. `JsonProcessor.get_objects` turns each element of the city into **parts** (`psdl_parts.ExportedCityElement`): roads, intersections, terrain patches, building lines, decals (`decals.py`), mesh instances and prop placers (`prop_placers.py`). The roads and intersections also register what the BAI needs (`exported_roads`, `traffic_intersections`), and the BAI network is built after them (see [The BAI](#the-bai)). `get_objects(traffic_only=True)` stops there, for the checks that need only the network and the room perimeters (`checks/validateOpponents`).
3. `scene.Scene` converts the parts once to the space of the writers (see [Coordinates](#coordinates)) and finds the rooms.
4. The writers (`writers/`) write the files from the scene. Each one is guarded (see [Errors](#errors)), so the others are written even if one fails.
5. The other files are written from the JSON directly (or the processor): prop rules, the PATHSETs of the city routes, CINFO and AIMAP, hudmap and race maps.
6. With `packAr`, the files are written to a temporary folder and packed (`ar_packer.py`).

## Modules

| Module | Content |
|---|---|
| `export.py` | The entry point: the steps above (`Exporter`) |
| `options.py` | The arguments: the `Files/python` folder, the input JSON, the chosen file, then a 0/1 value for each flag of `settings.json`, in its order (the program passes them so) |
| `json_processor.py` | The procedural elements as parts: the PSDL roads and their sections, intersections, terrain patches, buildings, mesh instances; the blocks (rooms) and their perimeters |
| `decals.py` | The decals (`decal`, `decalSingle`) as `DECAL` parts |
| `prop_placers.py` | The prop lines and polygons as `PTH` parts |
| `psdl_parts.py` | `ExportedCityElement` and the helpers for the sections of the parts |
| `scene.py` | `Scene`: the parts in the space of the writers, the rooms |
| `traffic/model.py` | The BAI: `BaiNetwork`, `BaiRoad`, `BaiSide`, `BaiRoadEnd`, `BaiIntersection` |
| `traffic/paths.py` | The paths of a procedural road (edges, curbs, lanes, sidewalks, rails) |
| `traffic/network.py` | `BaiNetworkBuilder`: the BAI roads and intersections from the exported roads and intersections |
| `traffic/rails.py` | The curves joining the cable car rails through an intersection (for `converters/generateRailDecals`) |
| `traffic/opponents.py` | The route of the race opponents as the game drives it, on the BAI network (for `checks/validateOpponents` and the warnings of the AIMAP export, see `docs/agents/races-and-state.md`) |
| `writers/` | The writers of the game files: `psdl_writer`, `cpvs_writer`, `inst_writer`, `bai_writer`, `pathset_writer`, `decal_writer`, `pkg_writer`, `tex_writer`, with `file_io` (binary output) and `report` (warnings and errors) |
| `cinfo_aimap_export.py`, `race_elements.py`, `hudmap_export.py`, `prop_rules_export.py`, `train_export.py`, `boat_export.py`, `bridge_export.py`, `parked_car_export.py`, `route_pathset.py` | The files written from the JSON |
| `generated_export.py`, `generated/` | The generated files (road low LOD textures, bridge models), written in the export folder before the other files, their paths set in the data; `generated/` is shared with the editor's generators (`generators/` of the core), `.km2-generated.json` lists what the exports wrote |
| `custom_element_conversion.py` | The helpers of the converters of the core (`Converter`, `Output`, `run`) |
| `tools/` | The check tools and the developer tests (see [Checks](#checks)) |

The writers in `writers/` were first written for a Blender add-on, then kept in this repository only (their MIT license is the one of the core).

## Coordinates

- **Program** (the JSON, the parts, the BAI model): left-handed, Y up, +Z forward, +X right.
- **Writers** (`Scene`): the program space with Y and Z exchanged, `(x, z, y)`: Z up, X not mirrored. `scene.to_writer_space` converts positions (rounded to 32 bit floats, as in the game files) and `scene.to_writer_rotation` quaternions (the program's `(x, y, z, w)` becomes `(-w, x, z, y)`).
- **Game files**: `writers/file_io.BinaryFileHelper.write_vec3` writes `(-x, z, y)` from the writer space, so the game has the X of the program mirrored (`game = (-x, y, z)`). The PATHSET, PKG and decal writers do the same.

Exchanging Y and Z mirrors the geometry, so the scene reverses the triangles to keep their winding: the whole flat list for the surfaces (which also reverses the order of the triangles, followed by the perimeter tracer), each submesh for the PKG meshes.

## Parts

A part is named `<prefix,><room>_<TYPE>`: the room (block) number, 0 for the parts outside of the rooms, and the type. The optional prefix keeps parts apart in the order (see below). The textures are a comma-separated list (`mat`), which the scene turns into the properties `texture0..N` (before the own properties of the part). All the properties are strings.

| Type | What | Main properties |
|---|---|---|
| `ROADS`, `ROADSN` | Road with sidewalks (with/without the sidewalk mesh) | `prop_rule`, `original_id`, `echo`, `warp` |
| `ROADN` | Road without sidewalks | |
| `ROADD`, `ROADDN` | Divided road | `divider_type`, `divider_param`, `caps` |
| `RAIL`, `RAILC` | Road and junction tunnels (`RAILC` also from the `rail` elements, see below) | `road_name`, `is_rail`, `curved_sides`, `is_wall`, offsets and caps |
| `SW`, `CW` | Sidewalk strip, crosswalk | `cap` |
| `IS`, `BLOCK`, `NUL` | Road surface, terrain, invisible surface (triangle fans) | `no_coplanar_fix` |
| `ROOF`, `FAC`, `FACB`, `SLIVER` | Roof, facade, facade bound, sliver | `tiling`, `u_tiling`, `v_tiling` |
| `INST` | A mesh instance (position, rotation, scale) | `object`, `flags` |
| `PKG` | A mesh exported to a PKG (with its LODs and bound) | `pkg_name`, `lod_name` |
| `PTH` | A prop (`flags` 0, 1) or a prop line (`flags` 2) of the PATHSET | `object`, `flags`, `spacing`, `race` |
| `DECAL` | A decal strip (pairs of points across it) | `texture`, `strip_pairs` |

`original_name` is the name of the element a part comes from (warnings name it), and `source` its `(kind, id)`.

The `rail` custom elements (splines through perimeter points, following the perimeters between their points, see `lua/rails.lua`) become `RAILC` parts after all the rooms are known (`get_rail` in `json_processor.py`): the rail goes to the room of the element of its `room` reference (`element_blocks`, filled as the roads, intersections and patches are exported), and only its edges on that room's perimeter count (positions within 1 cm). A rail without a room (its element deleted) falls back to the room whose perimeter has each edge, an edge of two rooms going to the one on the right of the rail's direction (seen from above, a rail goes clockwise around its room, as the old patch border meshes did). Each run of consecutive edges in one room is a `RAILC` part; the edges on no room perimeter, or on a patch exported to PKG, are left out (with a warning for the first ones). The writer then flags the perimeter edges of the room the part covers. Migration 9 turned the border meshes of the patches into `rail` elements, with their patch as `room`.

**Order.** The scene sorts the parts by name, keeping their order otherwise. This sets the order of the INST objects (`<index>,<room>_INST`, in lexicographic order of the index), of the PATHSET types, of the PKG groups and of the facades in a room. Within a room, the PSDL writer orders the parts by type (`PSDLWriter.block_sorted_by_type`).

**Rooms.** The PSDL writes only the rooms that have surfaces (`scene.is_surface`), in the order of their numbers: `Scene.blocks` lists them, and `Scene.block_index` gives the index of a room number in the PSDL. The PSDL, INST and BAI writers use the same table.

## The BAI

The BAI is built as a model (`traffic/model.py`) before being written, from the roads and intersections as the processor exports them.

**Paths of a road** (`traffic/paths.py`). A BAI road has a right side (the lanes going from its end to its start) and a left side (the ones from its start to its end), each with its outer edge, curb (the inner edge of the sidewalk, or the outer edge without sidewalks), lanes (inner first), pedestrian path and cable car rail. Every polyline goes from the start to the end, with a point per section of the road. The right side of the BAI is the left one of the road in the program (the sections of the PSDL roads go from its left to its right), so its pedestrians are the ones of `disableLeftPedestrians`. The edges and curbs are vertices of the road mesh (`bai_sections`, the vertices of `get_road_sections_layout`). The other paths are the ones drawn in the editor, the traffic lanes of the road type (`trafficLanes` in the core, named `traffic_<type>_<component>_<list>_<lane>` by the program), 1 cm below where they're drawn:

| Type | Path | Fallback |
|---|---|---|
| 1, 2 | Forward and backward lanes | Spread evenly between the curbs (or the curbs and the divider), with a warning |
| 0 | Pedestrians | Midway between the curb and the outer edge, with a warning if the road has sidewalks there |
| 3, 4 | Cable car rails (with `cableCarLine`) | At `cableCarOffset` from the centre, with a warning |

A path is used only when the number of paths matches and each has a point per section; the side of the pedestrian paths and rails is found from their position across the road. The editor's pedestrian paths are on the sidewalk surface, 7.5 cm higher than the stock files, which put the sidewalk centre midway between the curb at road level and the outer edge.

**Network** (`traffic/network.py`, `BaiNetworkBuilder.build`):

- **Seamless intersections** (two roads joined without a surface): roads with the same layout and the same section at the joint are a single BAI road through the rooms of all of them (a *chain*, `chains`); other ones get a two-road intersection in the room of one of the roads, where the vehicles never stop (rule 3).
- A chain becomes a BAI road only if it has a BAI intersection at both ends.
- **Intersections with more than 11 roads** (the game crashes on them, see the agent notes) become a ring of smaller intersections in the same room, joined by two-way ring roads (`split_intersection`). The ring roads come after the other roads.
- The roads of an intersection are listed counterclockwise (`entries`: the generator orders them clockwise), each with the end of the BAI road on it; `BaiIntersection.position_of` gives the position of a road end in the list.
- **Traffic lights** placed by hand (the `startTrafficLight`/`endTrafficLight` objects of the roads) are attached to their road end (`attach_traffic_light`), the others are placed by the writer on the opposite road, as in the game.

**Writer** (`writers/bai_writer.py`): converts each road to the space of the writer, resamples its sections (`resampled_parameters`: a section 15 m from each end, sections 2 m around the sharp corners, at least 4), moves the pedestrian points near the corners back along the sides (`spread_corner_points`, for the way the game's pedestrians aim), writes the frames, distances, offsets and lane boundaries of each section as the stock files have them, the road ends, the intersections, then the roads near each room (culling, by bounding box or, with `bai_accurateCulling`, by distance).

The hudmap arrows of the one-way roads use the chains and the paths of the builder (`hudmap_export.get_arrows`).

## The CPVS

`writers/cpvs_writer.py` writes `city/<city>.cpvs`, the rooms visible from each room (format in the agent notes), under the `cpvs` flag, with the `FAST` or (`cpvs_accurate`) `ACCURATE` parameters. `CPVSGenerator` works on plain arrays (z up), so that `tools/cpvs_check.py --stock` can feed it a stock PSDL; `CPVSWriter.inputs` makes them from the scene:

- **Rooms**: `Scene.blocks`, in the order of the PSDL. Their **floors** (the flat triangles of the road, sidewalk, crosswalk, intersection, terrain and invisible surfaces) hold the viewpoints. Their **targets** are all their surfaces, their PKG meshes and the top of the box of their INST meshes (the `bounds` property that `get_mesh_instance` takes from the mesh dictionary). A room is visible if a target is.
- **Neighbours**: the rooms sharing a vertex (within 5 cm), always visible, as in the stock files.
- **Occluders**: the facade bounds (`FACB`) and the ground surfaces, solid below them, and the roofs, solid down to the ground. The objects are not occluders, and neither are the facades (`FAC`, `SLIVER`: their bounds stand for them).

The generator rasterizes the occluders as a height field: the highest occluder of each cell (4 m). The walls are sampled densely, the other triangles at the centres of the cells and along their edges. A cell is a **passage**, with no occluder (and so are the cells around it), when a floor at its centre is lower than a ground occluder there by more than 3 m (under a bridge, an overpass, terrain over a tunnel). The floors and the occluders are compared at the same points, so the edge of a raised block next to a street isn't a passage. The targets are the highest point of each room in cells of 8 m (if a lower point of a column is visible, the higher one is too), grouped by room and 64 m tile.

For each room, the viewpoints are points of its floors, by farthest point sampling (the first near the middle; points in a cell of an occluder only if there are no others), at each eye height. From each viewpoint, rays cast around it (`cast`) keep the running maximum of the elevation `(top - eye) / distance` of the cells they cross: the horizon. The steps are one cell long up to 128 cells, then twice as long every time the distance doubles, on grids of cells twice as large where each cell is the lowest of the four below it (it hides only what they all hide). A ray stops when no target can be above its horizon, or when it leaves the city. From a viewpoint inside an occluder (under a roof), the occluders the rays start in are left out. A group of targets is skipped when its highest point, at its nearest distance, is below the lowest horizon across it (`possibly_visible`). Otherwise each target is visible if its elevation is above the lower horizon of the two rays around it, before the cell of the target and the one before it.

Everything conservative goes towards more visible rooms: missed occluders, the passages, the lower of two rays, the min-pooled far grids.

## Errors

The exporter reports the problems with `Files/python/ExportReport.py` of the program, through `writers/report.py` (which prints them, and raises the errors without `ExportReport`).

- Every `Warning:` is a warning of the report, with the element when its name is known (`original_name` of the parts, without the `[shoulder]`-like suffix: `report.element_name`).
- `JsonProcessor.guarded_element` exports each road, intersection, terrain patch, building line, mesh instance and prop placer on its own: one that fails is reported and left out, with what it had added (its parts and its BAI records).
- The PSDL writer writes a room that fails (e.g. a perimeter error) empty, so that the other rooms keep their index, and goes on.
- Each file is written even if one before it failed (`report.guarded`), and the export fails at the end if there were errors.

## Checks

- `tools/psdl_check.py` (perimeter spikes and slits, prop-room texture indices), `tools/bai_check.py` (`--lint`: the conventions of the stock files; `--derive`: the values computed again from the splines), `tools/decal_check.py`, `tools/cpvs_check.py` (the layout against the PSDL, self and neighbours visible; `--compare`; `--stock`: the generator on a stock PSDL against its CPVS): check the game files.
- `tools/_test_*.py`: short synthetic checks of the writers and of the files written from the JSON (`python <file>` with the program's Python).
- The fast loop and the equivalence checks are in the agent notes ([Exporter workflow and engine limits](agents/exporting.md)).
