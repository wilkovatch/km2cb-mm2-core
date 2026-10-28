# AGENTS.md

Guidance for AI coding agents (and humans) working on the **Midtown Madness 2 core** of km2 City Builder. The core is installed in the builder's `Files/cores/MidtownMadness2`. Read the builder's [AGENTS.md](../../../AGENTS.md) first for the general rules (generic base builder, commits, versions, short tests, building, self-tests). [README.md](README.md) is the user-facing overview of the core; this file collects the MM2 facts and workflows that aren't obvious from the code.

## References

- MM2 file format specifications (needed for any change to the exporters): https://github.com/Dummiesman/angel-file-formats/tree/master/Midtown%20Madness%202. The PKG reference is https://github.com/Dummiesman/PKGImportExport.
- Machine-specific locations (the game install, the extracted stock data, the psdl-viewer) are in the builder's gitignored `CLAUDE.local.md`. Don't scan drives for them.

## Game data

Never commit original game data (`city/materials.csv`, stock `.pkg`/`.tex`/bounds, ...) to this repo. The user provides these files in the builder's gitignored `Files/common/MidtownMadness2/` folder, which mirrors the game layout (`geometry/`, `texture/`, `city/`, `jpg/`, `tune/banger/`) and is created from this core's `baseCommon/`, where only `_put ... here` placeholder files are tracked. When such a file is missing, warn and fall back to a default.

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
- The exporters end with `input()`. Without a console, the builder's `PythonManager.RunScriptTask` feeds newlines on stdin.
- A finished export deletes its `.bin`, so "no `.bin` left" is the reliable success test (a Python traceback goes to stderr, which neither `pythonLog.txt` nor the API `output` captures).
- Exports land in `<path dir>/city/<name>.psdl` (game folder layout from `output_layout.py`; tune, race, geometry, bound, texture, jpg go next to `city`).
- The bundled Python needs `pythonInfo/requirements.txt` (e.g. Pillow for the hudmap). CLI sessions skip the builder's Python check, so install them by hand.

## Low-level elements

The MM2 low-level elements are the PSDL attributes (the generic mechanism is in the builder's `wiki/Core-Low-Level-Elements.md`, the MM2 specifics in the README). Equivalence check: export, convert everything, export again, compare PSDL room by room and BAI. The expected result is 0 differences.

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

**Props (bangers):** the game draws a banger at `position + rotation * CG` (`CG` of `tune/banger/<pkg>.dgBangerData`, MM2 coordinates, x mirrored in the builder), for the pathset props, the prop rules and the traffic lights; without banger data at the position. The editor does the same through `server/mesh_transforms.py` (the builder's `meshTransform` placement rule), so the exported position is the placement point. The CG is usually `-minY` of the mesh, but not always (fences are drawn from one end, `sp_cenotaph_gen_l` 4 m forward, `sp_chinagate_f` has CG 0 and sinks 7 m). Same rule as the psdl-viewer's `BangerTransform`.

**Textures and slivers:** facade/sliver V runs from the top (v=0 = texture top in the editor; the psdl-viewer uses the flipped convention). Game sliver rule: u = floor(len·s + 0.5), v = (top - y)·s. Stock sliver scales are always positive. Stock city PKGs use byte shaders `0x81` with colours 229/229/0 and shininess 0.25.

**Stock data:** SF cable cars are BAI `nTrams` = 1 on both sides, with the rail 2.5 m from the centre line. London's visible trains are `gizTrain` gizmos from `race/london/london_train.pathset`. Stock cities are compressed about 0.3-0.5x relative to real scale.

Reverse-engineering setup: install capstone + pefile with `pip install --target <scratch dir>`. Don't name a script `dis.py`, because it shadows the stdlib module capstone imports.
