# Game assets and city importing

Read the [repository instructions](../../AGENTS.md) first. Paths and command examples below are relative to this repository root unless another working directory is specified. Builder CLI and self-test commands run from the builder root.

For imported geometry and BAI behavior, also read [PSDL and BAI](psdl-and-bai.md); for prop mappings, read [Props and parked cars](props-and-parked-cars.md). Run builder-side import checks using the builder's [testing notes](../../../../../docs/agents/testing.md).

## Stock game asset importer

The Scripts menu's **Import MM2 game assets** (`scripts/importGameAssets`) imports from the user's `MM2CORE.AR` and `MM2TEX.AR`. These are **DAVE**, not the ZIP archives written by `exporters/psdl/ar_packer.py`. The reader uses the index at `0x800`, padded index/name blocks and raw DEFLATE (`wbits=-15`) when stored and original sizes differ. It supports ASCII DAVE filenames only; `Dave` compressed filenames and ZIP mods are intentionally rejected. Format reference: https://github.com/EdnessP/scripts/blob/main/midnight-club/dave.py.

The importer selects only PKG/MTX geometry, TEX/TGA textures, banger tuning and `city/materials.csv`; no mods, loose overrides, bounds, city/race files or JPG/map frame. New paths are lowercase; existing paths are resolved case-insensitively. Destination is derived from the installed core, never the script's working directory. It skips existing files unless overwrite is checked, validates both archive indexes before writing, then publishes validated payloads through temporary sibling files and `os.replace`. Filesystem writes cannot be undone (`transaction: false`); cancellation kills Python and leaves completed files, possibly with a harmless `.km2-mm2-import-*.tmp` file. Reruns skip completed files. Save and reopen the city after importing to refresh asset caches.

Run the short synthetic tests with `python scripts/importGameAssets/_test_import_assets.py` from the core folder (standard library only). Test fixtures and outputs live in a temporary directory; use a writable `TMP`/`TEMP` if the sandbox's default temp directory is restricted. Stock checks should sample about ten entries with a fixed seed and compare them to the extracted data configured in the builder's local instructions; do not extract the entire game for a test. Helper/test filenames start with `_` so they cannot appear as separate Scripts-menu entries. Menu and runtime strings are in the script's `strings/en-US.json`.

## City importer

`Scripts → Import MM2 city` lives in `scripts/importCity`. `_formats.py` is bounded binary reading, `_mapping.py` creates converter-shaped custom element payloads, `_companions.py` handles CSV/settings/transforms, and `main.py` is the transactional API adapter. Unknown attribute sizes fail rather than guessing. The viewer-derived readers retain `LICENSE-viewer.txt`.

PSDL type 1 stores regular sidewalk pairs as **inner, outer**. Exactly four references beginning with `0,0` or `1,1` describe an end cap: the first pair is a marker (start/end), not city vertices, and the last pair maps to `sidewalkCap.a/b`, with `which` 1/2. Treating these as regular strips pulls geometry toward vertices 0/1. `_test_sidewalks.py` runs through the builder script CLI with `KM2_IMPORT_TEST_FOLDER`; optional `KM2_MM2_SOURCE_ROOT` adds ten fixed-seed SF/London sidewalk attributes. It checks generated geometry, undo/redo, save/reload and native PSDL re-export without loading a whole stock city.

BAI remains approximate: report lost room memberships and train splines; do not advertise complete stock round-trip equivalence from close lane geometry. `_roundtrip_check.py` reports pedestrian displacement separately. Keep stock checks bounded (five fixed-seed routes per city) and assets/output in scratch folders. The importer adds asset search paths outside undo and references source files without copying them.

User-visible behavior: the import appends to the open city as one undo step (rolled back on failure or cancellation); rooms, attributes and AI become custom elements sharing source vertices and matching existing anchors, INST objects and point props become mesh instances. Single-room prop rules stay attached to road custom elements, rules spanning rooms become standalone **Prop rules** with boundary ribbons and road-center distance references. Native `props.pathset` line strips stay procedural and re-export as type-2 strips only when the evaluated placement matches the format's spacing/orientation (1 cm position, 0.1° yaw tolerance), otherwise as individual props. Source city settings and traffic-model lists apply unless **Apply source city settings** is off. BAI distances, frames, sidewalk centers, lights and culling are regenerated, multi-room route membership is reduced to one owner and arbitrary BAI train splines are omitted; the console reports these approximations.

### Importer checks

- `python scripts/importCity/_test_import_city.py`: short synthetic parser/mapping/strip tests.
- `_test_builder.py`: runs through the builder's script CLI with `KM2_IMPORT_TEST_FOLDER` naming a new scratch folder; covers import, generic ribbon sampling, undo/redo, save/reload, settings, INST transforms and native strip re-export.
- `_roundtrip_check.py source/city/name.psdl export/city/name.psdl --sample 10 --seed 42`: JSON semantic audit to stdout; `--out` saves it, `--strict` fails on compared differences.
- `_test_stock.py`: optional bounded check of five routes per stock city, with `KM2_MM2_SOURCE_ROOT` pointing at the extracted game root.
- `_test_sidewalks.py`: see above.

Use writable `TMP`/`TEMP` where needed. None of these requires committing stock assets.

Baseline of the fixed-seed ten-route SF/London check: sampled lane counts and ambient permissions are preserved, with lane-position differences below 0.03 mm. Exporter vertex welding moves some surface vertices by up to 3.3 cm. On two curved London routes the sidewalk curves stay close, but their samples at corresponding road sections shift by 10–14 m as sections are regenerated, so close lanes alone don't establish equivalent pedestrian or traffic behavior. This check doesn't replace an in-game check of a whole imported city.
