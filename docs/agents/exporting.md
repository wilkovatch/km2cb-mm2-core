# Exporter workflow and engine limits

Read the [repository instructions](../../AGENTS.md) first. Paths and command examples below are relative to this repository root unless another working directory is specified. Builder CLI and self-test commands run from the builder root.

Read this topic for any exporter change. Also read the relevant format/feature topics from the [core index](../../AGENTS.md#read-before-working) and the builder's [development](../../../../../docs/agents/development.md) and [testing](../../../../../docs/agents/testing.md) notes.

## Self-contained exporter

The structure of the exporter (pipeline, modules, coordinate spaces, parts, the BAI model and its paths, error handling) is documented in [The PSDL exporter](../exporter.md): read it before changing the exporter, and keep it up to date. Exporter changes can affect the builder (C# and `Files/python`) too. The writers in `exporters/psdl/writers` are maintained here only; there is no intermediate file between the processor and the writers.

When stashing to compare against old behaviour, stash both the builder repo and this repo. This repo keeps its own older stashes, so pop only yours.

Useful tools: `exporters/psdl/tools/psdl_check.py` (perimeter spikes/slits, prop-room texture indices), `bai_check.py --lint` (BAI sanity, max 11 roads per intersection), `decal_check.py`, `cpvs_check.py` (CPVS layout against the PSDL, `--compare`, `--stock` calibration; see the CPVS notes below).

Fast exporter loop without the game (from the builder folder): `-- export-json <city> --out x.json`, then run this core's `exporters/psdl/export.py <Files/python> x.json x.psdl <flags...>` directly with the builder's `python/python.exe`, one 0/1 value per flag of `exporters/psdl/settings.json`, in its order (`options.py` names the expected ones when the count is wrong). A BAI-only export of a large city takes about 3 s.

Equivalence check for a refactoring: copy the current `exporters/psdl` (with `server` and `fonts`, which it reads two folders up) to a scratch folder, run both exporters on the same JSON files with the same flags and compare the output trees byte by byte (an `.ar` stores file times: compare its entries). `tools/bai_check.py`'s `read_bai` reads both BAIs for a field-by-field comparison when a change is intended.

Exporter gotchas:

- The PSDL exporter waits for Enter only when stdin is a terminal, and tolerates EOF at that prompt. Linux console launches can inherit closed or redirected stdin; an optional pause must not turn a completed export into an error or mask a real failure. Without a console, the builder's `PythonManager.RunScriptTask` also feeds newlines on stdin for older exporters.
- The exit code is the success test: 1 for an exception or for errors in the report (a Python traceback goes to stderr, which neither `pythonLog.txt` nor the API `output` captures).
- Exports land in `<path dir>/city/<name>.psdl` (game folder layout from `output_layout.py`; tune, race, geometry, bound, texture, jpg go next to `city`).
- All PATHSET writers (props, decals, race props, parked cars, trains and boats) run under the `pathset` flag, independently of `cinfo_aimap`. Each city-route writer has its own error guard. Files written again are truncated or replaced, including shorter outputs; repeat-export checks are in `exporters/psdl/tools/_test_export_overwrite.py`.
- The bundled Python needs `pythonInfo/requirements.txt` (e.g. Pillow for the hudmap). CLI sessions skip the builder's Python check, so install them by hand.

## Midtown Madness 2 reference

Facts reverse-engineered from `midtown2.exe` and the stock files. They explain why exporter limits and workarounds exist.

**Engine limits and crashes** (first stop: `mm2.log` and `mm2hook.log` in the game folder):

| Symptom | Meaning |
|---|---|
| Ambient traffic crash (~0x53A0D2) | A BAI intersection with **> 11 roads** overflows a 10-entry stack array. The BAI writer warns (`MAX_INTERSECTION_ROADS = 11`) and json_processor splits such intersections into a ring of small BAI intersections (with a `key` property) |
| Crash 0x45da58 after "Placing props along road segments" | A room with a prop rule uses a texture index **>= 255**. The writer orders materials so prop-rule rooms come first and drops the props of rooms still over the limit |
| Crash 0x4a48d8 after "Loading objects", then FindHeap failed | Static geometry table overflow: **~600-650 unique INST/prop mesh names** (6 slots each, ~4096 total, no bounds check). `inst_writer` warns at 597 |
| `PHYS.DeclareMover : mover not even in city` | The player car is outside any PSDL room, one line per frame |
| `Vehicle %d did not have permission to traverse intersection` | FIFO road-end rule (0) violation. Stock SF uses FIFO only at 3-way ends |
| Crash 0x5440c5 (aiPath lane vehicle update), often with "FindHeap failed" | Lane vehicle count larger than the linked list. One cause found: the ambient turn dispatcher (0x539750) sends a car on a freeway road (BAI flag 4) that isn't in its outer lane to 0x539870, which takes the first freeway road around the intersection and copies the lane number **unclamped** (0x539942); `aiPath::AddVehicle` (0x5491c0) has no bounds check, so a freeway road feeding a freeway road with fewer lanes corrupts the heap. All freeway roads reachable from each other need the same lane count (stock SF/London: no violation). Not checked by the exporter yet |
| Cruise freezes after "Reset!!!" in `mm2.log` | The spawn of the player (call at 0x41fc56 to 0x413b70) retries a random BAI intersection **without limit** while its room flags have 0x2E or one of its roads has the alley (2) or freeway (4) BAI flag. A city needs one intersection with only ordinary roads (stock SF: 178 of 214). Not checked by the exporter yet |
| Road rooms drawn without road texture and divider walls | Seen on a 110-section road room (224 perimeter points, 450 attribute words); rooms of 57 sections looked right, stock rooms have at most 15 (a third-party city 48). The exact limit wasn't found (the perimeter count is a byte in memory, 255). `json_processor.split_long_road` exports a PSDL road of more than `MAX_ROAD_SECTIONS` (40) sections as consecutive rooms sharing the joint sections (divider and rail caps open there), one BAI road through all of them (`rooms` of its record), with a warning |
| PSDL perimeter spikes | Fixed in `psdl_writer` (`remove_spikes`). Lowering the area threshold is **not** the fix. Lint with `psdl_check.py` |

**Sky:** the game reads `city/<city>.sky` (0x464cb0, `"%s %f %f %f"`): the sky dome model, then a height, a camera height factor and a rotation speed (the dome is drawn at camera height * factor + height, 0x465150, and turns by speed * time radians, 0x464f90). Stock: `sky_dome 0 0.95 0.005` (SF), `sky_dome_l 0 0.95 0.005` (London). Without the file the sky is black. `cinfo_aimap_export.export_sky` writes it from the `sky*` city properties (stock SF values when unset).

**Road walls:** the road tunnel (type 9 subtype 3) follows the edges of the road attribute. (The removed "Sidewalks as shoulders" option, `flatSidewalk`, exported flat shoulders as separate `_BLOCK` parts beside a lanes-only road attribute, so its walls had to be perimeter tunnels; it played badly in the game and was removed on 2026-11-09, unused.) The writer's `RAILC` mask is the stock fixed size (10 words: flags, height, 2 zero words, 6 words of edge bits, so at most 96 perimeter edges per room; stock SF/London always use 10, also in 3 SF and 9 London road rooms). Collinear perimeter points are merged, so a straight side is a single flagged edge. Pieces of road through an intersection (`roadsThrough`) get no rails, as `rail_typeI` in the editor. A room with an intersection surface (`IS` part) is flagged as an intersection (16) even when pieces of road through it are `ROADN` (which set the road flag 8): with the road flag, Cruise found no intersection to start at (0x413b70 rejects room flags & 0x2E) and froze (2026-11-09, `process_block_parts`). They are at the height of their road: lowered by the sidewalk height only when the road is (`applyHeightAnywayI` = `applyHeightAnyway or (throughIntersection and hasSidewalks)`; until 2026-11-09 they were always lowered, so on roads without sidewalks they were a 15 cm step below the junction, which broke the junction perimeter ("Perimeter Error, retrying", empty `RAILC`). A junction corner of no length (two road mouths meeting at a point, e.g. diverging roads without crosswalks) gets no `RAILC`: it would be empty ("railc is empty").

**Zero-length junction corners:** two roads in line at an intersection (a 2-road junction, or the trunk of a diverge while it is being built) give corners of no length when the crosswalks are 0, or with raised sidewalks. The expressions of the junction components that divide by a length (`intersectionSidewalk` `percent`/`zSw`, `crosswalk` `cwAdjLen`) are guarded with `if(length > 0, ..., 0)`: unguarded, 0/0 made NaN vertices, thousands of "Vector3 cannot be normalized" warnings per rebuild and very slow scripted builds (fixed 2026-11-09).

Other limits: 511 unique textures per city. PSDL has no per-vertex UVs and max 65536 vertices. The PSDL texture count is names + 1.

**CPVS** (`city/<city>.cpvs`, checked on the stock `london.cpvs` and `sf.cpvs` with `tools/cpvs_check.py`):

- `PVS0`, `u32` = PSDL rooms + 2, then rooms + 1 `u32` offsets into the list data (the last one is the end). There is one list per PSDL room, in PSDL order. Each list has 2 bits per room, low bits first in each byte. Pair 0 is reserved (always 0), pair k is PSDL room k (from 1). `3` = visible; the stock files use only 0 and 3.
- RLE: a header with the top bit set is followed by `(h & 0x7f) + 1` literal bytes. A header with the top bit clear repeats the next byte **`h & 0x7f` times, without + 1**: Dummiesman's page and its example are off by one there. With this rule, the longest stock lists decode to exactly `ceil((rooms + 1) / 4)` bytes. The stock encoder leaves out trailing zero bytes (93% of the lists are shorter), and the exporter writes them in full.
- The stock sets are sparse and look sampled: London has a median of 52 visible rooms out of 1341, with visible rooms up to 1.7 km away. Only 60% of the pairs are symmetric, and the sets aren't closed over neighbours. Self and perimeter neighbours are visible (1340/1341 and 12460/12476). London's underground rooms (floors below -4 m, 355 of them) are visible from rooms 800 m away, even from the surface, so the stock sets aren't geometric visibility there.
- Calibration (`cpvs_check.py --stock <psdl>`): it computes the sets from the PSDL floors, facade bounds and roofs, plus the boxes of the INST objects (bounds read from the PKGs of the stock `geometry` folder with the core's `server/mesh_formats.py`), and compares them with the stock file. Recall is the share of stock-visible pairs that are also computed visible:

  | Mode | London (1341 rooms) | SF (1171 rooms) |
  |---|---|---|
  | fast | 80.4% recall, mean 146 visible (stock 62), 23.5 s | 86.0% recall, mean 226 (stock 82), 46.6 s |
  | accurate (120-room sample) | 87.7%, mean 212, about 0.11 s per room | 93.1%, mean 321, about 0.24 s per room |

  Recall grows with viewpoints and eye heights. A finer grid (2 m, 1 m) changes nothing. Without the London underground rooms, fast recall is 87% and accurate 92%. Most remaining misses would need an eye 30 m or more above the floor. The computed sets are 2-3 times larger than stock (they are conservative), so culling is weaker than stock.
- Not verified in game yet: whether the game uses the camera's room or the car's, what it does without a CPVS, and FPS gains.

## Reverse-engineering setup

Reverse-engineering setup: install capstone + pefile with `pip install --target <scratch dir>`. Don't name a script `dis.py`, because it shadows the stdlib module capstone imports.
