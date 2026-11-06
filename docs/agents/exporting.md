# Exporter workflow and engine limits

Read the [repository instructions](../../AGENTS.md) first. Paths and command examples below are relative to this repository root unless another working directory is specified. Builder CLI and self-test commands run from the builder root.

Read this topic for any exporter change. Also read the relevant format/feature topics from the [core index](../../AGENTS.md#read-before-working) and the builder's [development](../../../../../docs/agents/development.md) and [testing](../../../../../docs/agents/testing.md) notes.

## Self-contained exporter

The structure of the exporter (pipeline, modules, coordinate spaces, parts, the BAI model and its paths, error handling) is documented in [The PSDL exporter](../exporter.md): read it before changing the exporter, and keep it up to date. Exporter changes can affect the builder (C# and `Files/python`) too. The writers in `exporters/psdl/writers` are maintained here only; there is no intermediate file between the processor and the writers.

When stashing to compare against old behaviour, stash both the builder repo and this repo. This repo keeps its own older stashes, so pop only yours.

Useful tools: `exporters/psdl/tools/psdl_check.py` (perimeter spikes/slits, prop-room texture indices), `bai_check.py --lint` (BAI sanity, max 11 roads per intersection), `decal_check.py`.

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
| Crash 0x5440c5 (aiPath lane vehicle update) | Lane vehicle count larger than the linked list. Cause not pinned down |
| PSDL perimeter spikes | Fixed in `psdl_writer` (`remove_spikes`). Lowering the area threshold is **not** the fix. Lint with `psdl_check.py` |

Other limits: 511 unique textures per city. PSDL has no per-vertex UVs and max 65536 vertices. The PSDL texture count is names + 1.

## Reverse-engineering setup

Reverse-engineering setup: install capstone + pefile with `pip install --target <scratch dir>`. Don't name a script `dis.py`, because it shadows the stdlib module capstone imports.
