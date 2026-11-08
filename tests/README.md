# MM2 developer tests

The C# API and undo scenarios live here and are compiled on demand by the builder. No compiled test files are committed. Run commands from a built builder source checkout, with the .NET SDK available:

```text
python Tests/run_in_background.py "<godot console executable>" --path . --resolution 1152x648 -- selftest api <new scratch folder> --core MidtownMadness2
python Tests/run_in_background.py "<godot console executable>" --path . --resolution 1152x648 -- selftest api <new scratch folder> --core MidtownMadness2 --focus parkedCar
python Tests/run_in_background.py "<godot console executable>" --path . --resolution 1152x648 -- selftest undo <new scratch folder> --core MidtownMadness2 --mode new
```

The scratch city folder must be new for creation scenarios. Logs and screenshots are written next to it. Program settings are restored by the generic runner. Use a window for rendered, picking and mouse/keyboard checks. Follow the builder's rule to ask before multi-minute suites. This documentation was written with Claude Code and other AI agents.

## API groups

`TestProvider.cs` is the authoritative list of focuses. The command rejects unknown names. Existing `KM2_SELFTEST_FOCUS` commands still work; explicit `--focus` takes precedence.

| Focus | Coverage |
|---|---|
| `roads`, `creation`, `dependencies` | Roads, deferred API creation, shared points and attachment dependencies |
| `geometrylessRoads` | BAI-only roads: no meshes, intersections sized without them or without surface, picking, type changes, export JSON, validation warnings and the BAI of the exporter (`exporters/psdl/tools/_test_geometryless_roads.py` on the exported JSON) |
| `customElementPresets`, `listLabels`, `independentPoints` | Custom element presets, list-only labels and inline point storage |
| `splines`, `splineState`, `projection` | Decals and rails, curve components, spline instance values, history, reload and surface projection |
| `rails` | The `rail` elements (room perimeter railings): accepted targets, spans following the perimeters and road anchors, loops, reversing, history and export |
| `propPlacers`, `parkedCar` | Spline/polygon props, core callbacks and guides; single parked cars and native parked rows |
| `bridges` | Native preview modes/models, road-end attachments, mesh generation, race replacements, history and reload |
| `trains`, `boats`, `arrows`, `trafficLanes` | Native route previews, custom road curves, closed loops and direction/traffic geometry |
| `mapLabels`, `races`, `instMesh`, `heightmapScale`, `unicode` | Map labels, race containers/opponents (waypoints on intersections) and the opponent route check, INST editing, terrain scaling and Unicode persistence |
| `menus`, `meshTextures`, `meshPreviews`, `meshSelection` | Menu definitions, texture resolution, mesh preview UI and triangle selection |

The normal suite covers the API protocol, creation/editing, undo/redo, transactions, generators, Python/Lua scripting, type inheritance, merge/split, custom elements and their editors, export layout/maps, archives, validation, MCP and rendered checks. Some focused groups have independent setup and are not part of the normal sequence; run them when changing shared test setup or the runner.

The restored `parkedCar` group tests authored heights and manual **Project to ground**, placement, yaw, picking, history, race ownership, reload and native export. It must not reintroduce automatic surface following. The `bridges` group includes unique checks recovered from the older stash, adapted to the current mesh field.

`--focus incremental` and `--focus meshBenchmark` are explicit performance runs. The older `KM2_SELFTEST_INCREMENTAL=1` and `KM2_SELFTEST_MESH_SELECTION=benchmark` selectors remain supported; `KM2_SELFTEST_MESH_SELECTION=test` selects `meshSelection`. Asset benchmarks sample ten available meshes with seed 42.

## Undo modes

| Mode | Fixture and coverage |
|---|---|
| `new` | Fresh 2048 m terrain: element edits, snapshots, menu actions and road split/merge history |
| `split` | Fresh 2048 m terrain: road splitting, joining, backwards placement and visual split guides |
| `placement`, `height`, `rotation` | Fresh city: point selection/insertion, placement height/snapping and held-click rotation |
| `drag`, `dropdown` | Fresh city: numeric middle-drag and dropdown keyboard/wheel input |
| `guide` | Guide parsing/content/links and the panel's navigation, geometry and input; writes `guide_fixtures` screenshots |
| `props`, `ui`, `load`, `selection` | A disposable copy of an existing city: prop selection history, editor restoration, terrain undo and selection cleanup |

Input modes move a simulated cursor (the builder's `GameEngine.Input`), not the user's, and the window ignores the real keyboard and mouse. Launch windowed runs through the builder's `Tests/run_in_background.py` so the window doesn't take the focus. Keep the window at the documented resolution. Existing-city scenarios must identify their own fixture objects rather than depend on old registry IDs.

The pre-move baselines were one API prop-count failure and 35 undo failures. The API assertion now counts only exportable prop-line/polygon fixtures, excluding unrelated custom-road previews. The undo failure began with a terrain edit outside the former 512 m fixture; creation uses 2048 m and checks the edit bounds. See [agent test notes](../docs/agents/testing.md) for detailed fixture pitfalls and validation evidence, and the builder's [Core Testing](../../../../wiki/Core-Testing.md) for the provider contract.
