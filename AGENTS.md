# AGENTS.md

Guidance for AI coding agents (and humans) working on the **Midtown Madness 2 core** of km2 City Builder. The core is installed in the builder's `Files/cores/MidtownMadness2`. Read the builder's [AGENTS.md](../../../AGENTS.md) first for the general rules (generic base builder, commits, versions, short tests, building, self-tests). [README.md](README.md) is the user-facing overview of the core; this file collects the MM2 facts and workflows that aren't obvious from the code.

## References

- MM2 file format specifications (needed for any change to the exporters): https://github.com/Dummiesman/angel-file-formats/tree/master/Midtown%20Madness%202. The PKG reference is https://github.com/Dummiesman/PKGImportExport.
- Machine-specific locations (the game install, the extracted stock data, the psdl-viewer) are in the builder's gitignored `CLAUDE.local.md`. Don't scan drives for them.

## Game data

Never commit original game data (`city/materials.csv`, stock `.pkg`/`.tex`/bounds, ...) to this repo. The user provides these files in the builder's gitignored `Files/common/MidtownMadness2/` folder, which mirrors the game layout (`geometry/`, `texture/`, `city/`, `jpg/`, `tune/banger/`) and is created from this core's `baseCommon/`, where only `_put ... here` placeholder files are tracked. When such a file is missing, warn and fall back to a default.

The Scripts menu's **Import MM2 game assets** (`scripts/importGameAssets`) imports from the user's `MM2CORE.AR` and `MM2TEX.AR`. These are **DAVE**, not the ZIP archives written by `exporters/psdl/ar_packer.py`. The reader uses the index at `0x800`, padded index/name blocks and raw DEFLATE (`wbits=-15`) when stored and original sizes differ. It supports ASCII DAVE filenames only; `Dave` compressed filenames and ZIP mods are intentionally rejected. Format reference: https://github.com/EdnessP/scripts/blob/main/midnight-club/dave.py.

The importer selects only PKG/MTX geometry, TEX/TGA textures, banger tuning and `city/materials.csv`; no mods, loose overrides, bounds, city/race files or JPG/map frame. New paths are lowercase; existing paths are resolved case-insensitively. Destination is derived from the installed core, never the script's working directory. It skips existing files unless overwrite is checked, validates both archive indexes before writing, then publishes validated payloads through temporary sibling files and `os.replace`. Filesystem writes cannot be undone (`transaction: false`); cancellation kills Python and leaves completed files, possibly with a harmless `.km2-mm2-import-*.tmp` file. Reruns skip completed files. Save and reopen the city after importing to refresh asset caches.

Run the short synthetic tests with `python scripts/importGameAssets/_test_import_assets.py` from the core folder (standard library only). Test fixtures and outputs live in a temporary directory; use a writable `TMP`/`TEMP` if the sandbox's default temp directory is restricted. Stock checks should sample about ten entries with a fixed seed and compare them to the extracted data configured in the builder's local instructions; do not extract the entire game for a test. Helper/test filenames start with `_` so they cannot appear as separate Scripts-menu entries. Menu and runtime strings are in the script's `strings/en-US.json`.

## Coordinates

The builder and this core are left-handed, Y up, +Z forward, +X right. MM2 game files mirror X (MM2 x = -builder x, the exporters handle it). In-game north is -Z and east is +X.

## Exporter changes span three repos

1. the builder (C# program, `Files/python`),
2. this core (remote `wilkovatch/km2cb-mm2-core`),
3. the submodule `exporters/psdl/common` = [psdl-exporter-common](https://github.com/wilkovatch/psdl-exporter-common), **shared with the Blender plugin**. Keep it backwards-compatible. For example, `common/report.py` must keep the old behaviour (print warnings, re-raise errors) when there is no `ExportReport`, and PKG paths are optional arguments (the Blender plugin keeps `<city>_geometry`).

When stashing to compare against old behaviour, stash both the builder repo and this repo. This repo keeps its own older stashes, so pop only yours.

Useful tools: `exporters/psdl/tools/psdl_check.py` (perimeter spikes/slits, prop-room texture indices), `bai_check.py --lint` (BAI sanity, max 11 roads per intersection), `decal_check.py`.

Fast exporter loop without the game (from the builder folder): `-- export-json <city> --out x.json`, then run this core's `exporters/psdl/export.py <Files/python> x.json x.psdl <flags...>` directly with the builder's `python/python.exe`. A BAI-only export of a large city takes about 3 s.

Exporter gotchas:
- The PSDL exporter waits for Enter only when stdin is a terminal, and tolerates EOF at that prompt. Linux console launches can inherit closed or redirected stdin; an optional pause must not turn a completed export into an error or mask a real failure. Without a console, the builder's `PythonManager.RunScriptTask` also feeds newlines on stdin for older exporters.
- A finished export deletes its `.bin`, so "no `.bin` left" is the reliable success test (a Python traceback goes to stderr, which neither `pythonLog.txt` nor the API `output` captures).
- Exports land in `<path dir>/city/<name>.psdl` (game folder layout from `output_layout.py`; tune, race, geometry, bound, texture, jpg go next to `city`).
- The bundled Python needs `pythonInfo/requirements.txt` (e.g. Pillow for the hudmap). CLI sessions skip the builder's Python check, so install them by hand.

## Custom elements

Most MM2 custom elements are the PSDL attributes, the others are the decals and trains (the generic mechanism is in the builder's `wiki/Core-Custom-Elements.md`, the decals and trains in the README). Equivalence check: export, convert everything, export again, compare PSDL room by room and BAI. The expected result is 0 differences.

### PSDL attributes

The PSDL attributes are for testing, so the README doesn't document them. They are `creatable: false` (no Create menu entry) and the `ui.json` of the `psdl` types has no `convert:toPsdl` button: they are made by the `toPsdl` converter (API `elements.convert`), the importer (`Scripts → Import MM2 city`) and `customElement.create`.

- Roads, intersections, terrain patches and building lines of type `psdl` (not exported to PKG) can be converted to the PSDL attributes they are exported to (converter `toPsdl`, run with the scripting API `elements.convert`), to edit them one by one: each vertex of the PSDL is a control point. Converting doesn't change the export: the converter runs the exporter on the element and turns the parts it would write into the attributes.
- The attributes are in rooms (one per room of the element), each room a block of the PSDL; the parts of a building are in a group placed in the room where the building is when exported (Scripts > Assign building parts to rooms merges them into their rooms). The roads and intersections also get their BAI road or intersection, which can be edited too (lanes, rules, connections).
- A converted room gets its perimeter as the exporter follows it (with `simplifyPerimeter`). Since it is set, changing the shape of its contents (e.g. adding sections to a road) needs the perimeter to be computed again (Compute the perimeter from the contents, in the panel of the room) or removed.
- The BAI road of a converted road is Auto-calculated: when the road attributes converted with it are edited, its edges and curbs follow theirs (chained from room to room) and its lanes (as many as there are) are spread evenly between each curb and the middle of the road (or the dividers), as the exporter does when the lanes drawn in the editor can't be used. Its points can't be edited while it's on: uncheck Auto-calculated to edit them (the road attributes are then edited alone).
- The points of a converted building follow each other: the points above another one are on its vertical line, and the lowest points inside the top or bottom edge of a sliver or facade bound (the corners of the facades between the ends of a side) are on that edge, so moving a corner keeps the building together.
- A converted road gets the psdl props containers of its prop rule (the ghost keeps exporting the others).
- The converted roads and intersections stay as hidden ghosts, so that the other elements keep their shape; the panel of an attribute can bring the original element back.
- The `psdl` road type gives its intersections an anchor across each of its ends (`endAnchors`: the outer sidewalk edges, the curbs at road level and, with a divider, its sides), so all the points of the end section of a converted road stay on a procedural intersection and follow it.
- The dividers at the ends of a converted divided road follow the line between the curbs there (which it shares with the converted intersection), so they keep their places across the road when the intersection, or its room, is moved.
- Triangle fans, road triangle fans and roof triangle fans can be converted to each other. Road and roof fans keep all their vertices at the same height, facades stay vertical rectangles, the tops of facade bounds and slivers stay horizontal.
- The texture references are not elements: the exporter makes them from the textures of the attributes.
- The types are the attributes of the rooms of the PSDL (see the [file format](https://github.com/Dummiesman/angel-file-formats/blob/master/Midtown%20Madness%202/Room_attributes.md)) and the BAI elements; the control points are the vertices of the PSDL, the heights of the PSDL (facades, roofs, slivers) come from the positions of the points when exported:

  | Type | Attribute | Points |
  |---|---|---|
  | `room` | A room (block) of the PSDL: contains the attributes and the BAI elements. Echo, warp, hudmap category. Its `perimeter` (a closed array, drawn as a magenta line that can be clicked to select the room) is written as it is, in the order of its points, the neighbours being the rooms sharing its points (their attributes or perimeter); with `simplifyPerimeter` the points in a straight line that lead to no other room are left out, and the spikes, as for the perimeter the exporter finds when it has none (fewer than 3 points). The button *Compute the perimeter from the contents* (converter `roomPerimeter`) sets it to the one the exporter would find, with `simplifyPerimeter`. | `perimeter` |
  | `buildingGroup` | The parts of a building outside of a room: they go in the room found at `location` (or at `frontLocation` if there is none there), as the procedural buildings. The core script Assign building parts to rooms merges every group into its room. | `location`, `frontLocation` |
  | `roadWithSidewalks` | 0x00; props containers `right` and `left` (along the sidewalks) | `sections`: `leftSidewalk`, `leftRoad`, `rightRoad`, `rightSidewalk` |
  | `roadWithoutSidewalks` | 0x02 (or 0x00 without sidewalks) | `sections`: `left`, `right` |
  | `dividedRoad` | 0x08: the divider drawn as the procedural roads (flat: a strip whose texture repeats `dividerValue` times across it; elevated: `dividerValue` high, its top edges beveled by as much; wedged: 1 m high, 0.5 m narrower on each side at the top), the closed ends with the cap texture; props containers `right`, `left` and `middle` (on the flat and elevated dividers) | `sections`: `leftSidewalk`, `leftRoad`, `leftDivider`, `rightDivider`, `rightRoad`, `rightSidewalk` |
  | `roadTunnel` | 0x09 (subtype 3), before the road attribute of its `road` parameter | - |
  | `junctionTunnel` | 0x09 (subtype 0): walls on the edges of the perimeter of the room between consecutive points | `walls`: `points` |
  | `sidewalkStrip` | 0x01 | `sections`: `inner`, `outer` |
  | `sidewalkCap` | 0x01 end piece | `a`, `b` |
  | `crosswalk` | 0x04 | `p1` to `p4` (in the order of the PSDL) |
  | `triangleFan`, `roadTriangleFan`, `roofTriangleFan` | 0x06, 0x05 (written as 0x06 if not flat), 0x0c: the whole mesh, split in fans when exported. The road and roof fans keep all their vertices at the same height. | mesh |
  | `facade` | 0x0b, after its facade bound (`bound` parameter); a vertical rectangle | `bottomLeft`, `bottomRight`, `topLeft`, `topRight` |
  | `facadeBound` | 0x07 (`bothSides`: also in the room in front of it); the top edge horizontal, the bottom one can be slanted | the same |
  | `sliver` | 0x03; as the facade bounds | the same |
  | `baiRoad` | A road of the BAI: its lanes (the arrays are uniform), its intersections (a BAI intersection, or a procedural intersection: the BAI intersection replacing it if it is a ghost, otherwise the procedural intersection lists it among its roads, in their order around it), rules, pedestrians... `autoCalculated`: see above (`psdl.baiRoadPoints`). | `sections`: `rightEdge`, `rightCurb`, `backwardLanes`, `forwardLanes`, `leftCurb`, `leftEdge` |
  | `baiIntersection` | An intersection of the BAI, in its room: its roads are the BAI roads ending on it (and the procedural roads ending on the intersection it replaces), counterclockwise | `center` |

## Midtown Madness 2 reference

Facts reverse-engineered from `midtown2.exe` and the stock files. They explain why exporter limits and workarounds exist.

**Engine limits and crashes** (first stop: `mm2.log` and `mm2hook.log` in the game folder):

| Symptom | Meaning |
|---|---|
| Ambient traffic crash (~0x53A0D2) | A BAI intersection with **> 11 roads** overflows a 10-entry stack array. The BAI writer warns (`MAX_INTERSECTION_ROADS = 11`) and json_processor splits such intersections into a ring of small BAI intersections (with a `key` property) |
| Crash 0x45da58 after "Placing props along road segments" | A room with a prop rule uses a texture index **>= 255**. The writer orders materials so prop-rule blocks come first and drops the props of blocks still over the limit |
| Crash 0x4a48d8 after "Loading objects", then FindHeap failed | Static geometry table overflow: **~600-650 unique INST/prop mesh names** (6 slots each, ~4096 total, no bounds check). `inst_writer` warns at 597 |
| `PHYS.DeclareMover : mover not even in city` | The player car is outside any PSDL room, one line per frame |
| `Vehicle %d did not have permission to traverse intersection` | FIFO road-end rule (0) violation. Stock SF uses FIFO only at 3-way ends |
| Crash 0x5440c5 (aiPath lane vehicle update) | Lane vehicle count larger than the linked list. Cause not pinned down |
| PSDL perimeter spikes | Fixed in `psdl_writer` (`remove_spikes`). Lowering the area threshold is **not** the fix. Lint with `psdl_check.py` |

Other limits: 511 unique textures per city. PSDL has no per-vertex UVs and max 65536 vertices. The PSDL texture count is names + 1.

**Pedestrians (BAI sidewalks):** the walk target is evaluated 6 m ahead on an **unclamped** Hermite curve, so short sidewalk segments that turn make pedestrians fly off and circle. Segments touching a sharp corner need to be ≥ ~16 m. `bai_writer.spread_corner_points` moves only the sidewalk points; the 2 m car sections stay.

**BAI:** coordinates are (x, up, z) with x mirrored. The engine's room lookup returns the first intersection of a room before its roads, so don't put extra intersections in road rooms. For stock BAI derivation rules see the maintainer's psdl-viewer project, `Scripts/Formats/BaiFile.cs` (location in the builder's `CLAUDE.local.md`).

**Decals (`city/<city>/decals.pathset`, PTH1):** one path per decal, named after its texture (≤ 31 chars). It is drawn as one triangle strip of point pairs, lifted +0.01 m. U is 0/1 alternating, and V of pair k = round(|p[2k]-p[0]| / |p[0]-p[1]|), so pairs must sit at about whole tile distances. The decal is attached to the room containing midpoint(p0, p2) and drawn only when that room is visible, so split long strips. Winding: ((p1-p0)×(p2-p0)).y > 0 in MM2 coordinates. Paths with fewer than 3 points are skipped.

**Hudmap and menu maps:** `geometry/hudmap_<city>.pkg` uses chunk `H` with FVF 0x102 and one quad per tile at y=0. **`.tex` rows are stored bottom-up**, so flip a north-up image before writing. `tune/<city>.mmHudMap` holds the `Ocean Color` as RGB 0..1. Menu maps are `jpg/<city>_map*.jpg`, 242x184, with the map in about (8,5)-(236,179). An optional frame goes in `Files/common/MidtownMadness2/jpg/mapframe.jpg`. Map labels appear only on the jpgs.

**Props (bangers):** the game draws a banger at `position + rotation * CG` (`CG` of `tune/banger/<pkg>.dgBangerData`, MM2 coordinates, x mirrored in the builder), for the pathset props, the prop rules and the traffic lights; without banger data at the position. The editor does the same through `server/mesh_transforms.py` (the builder's `meshTransform` placement rule), so the exported position is the placement point. A mesh without a `.dgBangerData` gets no transform (`None`), so the editor falls back to `autoYOffset` (lowest point on the placement point). The CG is usually `-minY` of the mesh, but not always (fences are drawn from one end, `sp_cenotaph_gen_l` 4 m forward, `sp_chinagate_f` has CG 0 and sinks 7 m). Same rule as the psdl-viewer's `BangerTransform`.

**Textures and slivers:** facade/sliver V runs from the top (v=0 = texture top in the editor; the psdl-viewer uses the flipped convention). Game sliver rule: u = floor(len·s + 0.5), v = (top - y)·s. Stock sliver scales are always positive. Stock city PKGs use byte shaders `0x81` with colours 229/229/0 and shininess 0.25.

**Stock data:** SF cable cars are BAI `nTrams` = 1 on both sides, with the rail 2.5 m from the centre line. London's visible trains are `gizTrain` gizmos from `race/london/london_train.pathset`. Stock cities are compressed about 0.3-0.5x relative to real scale.

Reverse-engineering setup: install capstone + pefile with `pip install --target <scratch dir>`. Don't name a script `dis.py`, because it shadows the stdlib module capstone imports.

## City importer and standalone prop rules

`Scripts → Import MM2 city` lives in `scripts/importCity`. `_formats.py` is bounded binary reading, `_mapping.py` creates converter-shaped custom element payloads, `_companions.py` handles CSV/settings/transforms, and `main.py` is the transactional API adapter. Unknown attribute sizes fail rather than guessing. The viewer-derived readers retain `LICENSE-viewer.txt`.

PSDL type 1 stores regular sidewalk pairs as **inner, outer**. Exactly four references beginning with `0,0` or `1,1` describe an end cap: the first pair is a marker (start/end), not city vertices, and the last pair maps to `sidewalkCap.a/b`, with `which` 1/2. Treating these as regular strips pulls geometry toward vertices 0/1. `_test_sidewalks.py` runs through the builder script CLI with `KM2_IMPORT_TEST_FOLDER`; optional `KM2_MM2_SOURCE_ROOT` adds ten fixed-seed SF/London sidewalk attributes. It checks generated geometry, undo/redo, save/reload and native PSDL re-export without loading a whole stock city.

The base builder's reserved `__propPath` type uses custom element point/history/editor infrastructure, but has API kind `propPath` and separate `propPaths` save/export arrays. Its `data.propLines` are evaluated placements. Never apply native-road `psdl` suppression to these records. `exporters/psdl/prop_paths.py` compares native strip candidates with preview placements before choosing type 2; mismatches fall back to type 0/1. The common writer keeps separate strip records even for identical models/spacing. Changes to it still span the shared exporter submodule.

BAI remains approximate: report lost room memberships and train splines; do not advertise complete stock round-trip equivalence from close lane geometry. `_roundtrip_check.py` reports pedestrian displacement separately. Keep stock checks bounded (five fixed-seed routes per city) and assets/output in scratch folders. The importer adds asset search paths outside undo and references source files without copying them.

## Spline decals

`elements/customElements/decal` uses the generic spline evaluator and road JSON components, API kind `customElement`, points `spline`. `spline.pieces` in exported elements supplies unlifted strip edge pairs; `json_processor.get_decals` passes these as DECAL parts with `strip_pairs=1`. The shared writer retains its old centerline/width path for Blender. Core component UVs follow the game winding and rounded distance of the first pair; height offset is 0.01 m. Keep projection away from overlay layer 13 to avoid accumulating height on overlapping decals.

`converters/generateRailDecals` is non-replacing and creates independent low-poly decal splines across the selected intersection only. `lua/decals.canGenerateRails` controls button availability. Pairing uses the existing BAI `join_rails` rules. Repeated generation deliberately appends; users delete old decals manually. Migration 3 converts manual city-property decals and removes automatic rail settings without baking them. Update new-city template coreVersion with the core migration version. Focused synthetic checks: `python exporters/psdl/tools/_test_decals.py`; keep stock assets out of fixtures.

The focused builder integration uses `KM2_SELFTEST_FOCUS=splines` with `selftest api <new folder>` (about 6 s windowed). To compare preview geometry/UVs with a real exported PATHSET, use `python exporters/psdl/tools/_test_decals.py --preview <export-json file> <decals.pathset>`.

## Train splines

`elements/customElements/train` uses the shared core curve registry (`splineTypes.json`, ID 3, `mm2Train`), allowed only by that type. Roads and decals retain their own allowlists. `lua/trains.lua` reproduces train Hermite X/Z, fixed 0.5 tangents, wrapped neighbor lookup and linear Y. Export the authored `points.spline`, never evaluated sections. Empty/two-point paths remain editable but cannot be exported as moving trains. Import retains incomplete type-2 paths with warnings. No original stock data belongs in fixtures.

Reference executable SHA256: `992c53c9250cf822b44bf4a4013bd5805229bbbeb7b478a4c2556531bc5340f3`. `57A530` builds tangents, `57A370` evaluates Hermite, `57A6D0`/`57A710` wrap neighbors; `578A61..578A9F` override train Y. Comparing 295 positions from London's eight stock routes uses isolated emulation, not game execution. The static route preview does not model reversal timing or body/room/model offsets.

Migration 4 converts `cityProperties.trainLines`, preserving incomplete routes, existing IDs and unrelated data through the normal versioned backup mechanism. New templates use coreVersion 4 in `templates/_common/preferences.json`. Focused checks: `python exporters/psdl/tools/_test_trains.py`; builder integration: `KM2_SELFTEST_FOCUS=trains` with `selftest api <new folder>`. The integration also tests a temporary synthetic road curve and its split/merge callbacks, restoring the core registry and removing its test module/type in a finally block. An optional `KM2_TRAIN_REFERENCE` points to scratch JSON with native-coordinate points and emulated `{t,position}` samples; never commit it.
