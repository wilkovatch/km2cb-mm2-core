# MM2 developer tests

Run commands from the builder root. Read the builder [testing instructions](../../../../../docs/agents/testing.md), then [tests/README.md](../../tests/README.md) for the available commands. Scenario sources live in this core; only the generic loader and test contract live in the builder.

### `selftest api <new folder>` (`tests/Api/ApiSelfTest.cs`)

Creates an MM2 SF city and drives it only through JSON API commands. It covers elements, anchors, terrain, undo/redo, transactions, generators, Python/Lua scripting, type inheritance, merge/split, seamless intersections, decals, export layout/hudmap, `.ar` packing, rendering, validation, MCP and custom elements. Writes `api_selftest.log`.

```
<godot console exe> --path . --resolution 1152x648 -- selftest api "<scratch>/api/city"     # windowed (also saves screenshots)
<godot console exe> --headless --path . -- selftest api "<scratch>/api/city"               # headless (skips the view checks)
```

The pre-move baseline was 1513 passing API checks and one prop-count assertion failure. The moved suite restricts that assertion to exportable prop-line and prop-polygon fixtures. Full-suite validation is required after changes to the runner or shared fixture setup.

Verified 2026-11-06 after the move: **1567 OK, 0 failures** in the full windowed API run; all 27 non-benchmark API focus groups passed. All 12 undo modes passed, including **198 OK, 0 failures** in `new` and **174 OK, 0 failures** in `split`. These two undo runs take about two minutes each with the complete terrain fixture. Mouse-driven modes ran with desktop access; sandbox cursor-query denials were verified separately. The generic builder runner passed 19 synthetic-core checks. No in-game verification is implied.

- `InheritedTypes` temporarily creates `Files/cores/MidtownMadness2/elements/roads/zzInheritTest`. If a run is killed, delete that folder by hand.
- A run with failures has exited with 132 (SIGILL) during Godot's shutdown finalizers. Clean runs exit 0.
- A run that stops without an error (no log, the window idle) is an API reply that never comes: `SettleProjectedSplines` (awaited by the dispatcher after each command while projected splines exist) waits until an update rebuilds no road, intersection or patch, so an element reporting a change at every update stalls it (e.g. a border mesh state never flagged unchanged). Run without `--quiet` to see the `[api-selftest]` lines up to the stuck step.
- Empty ObjectState arrays vanish on JSON re-read, so compare `[]` and missing as equal.
- `city.exportJson` ids are indices in the manager lists, not API ids. Ids change after a reload, so re-list (or compare by name).
- An API `Call` flushes and resets the elements' editing state, and a change closes the open editors (as before an undo). To test a GUI action with undo, run the GUI steps first, then `city.flush`, then take the snapshots (`CheckGuiUndo` in `BaiConnections`), not `CheckUndo` around them.
- The custom element panel gets its element from the click mode (`GetPlacer()` is `terrainClick.modifier as CustomElementPlacer`): a temporary click mode (e.g. `ReferencePicker`) must restore the previous one before changing the element. While the point transform panel (M) is open the modifier is null; `CityBuilderMenuBar.ControlPointOwnerCustomElement` gives the element.
- Every menu entry and panel button runs inside `UndoManager.Record` (`IsBusy` is true), so a `RunLong` API call made synchronously from a GUI action fails with "another operation is running". GUI code must yield a frame first, and tests of GUI actions should go through `UndoManager.Record` like the menu does.
- Panel checks: call `panel.Update()`, not `placer.onFrame` (which returns early when nothing changed).
- Read core settings like `allowYaw`/`allowRoll` from the type instead of hardcoding them; the maintainer toggles them locally.
- Independent points have no registry ID; whole-city undo snapshots capture them through their owner, rather than reporting them as unregistered elements.
- The existing-city terrain mode checks no-op strokes without undoing older history, and requires one history entry for each actual brush stroke.
- Rotation checks use the native 15-degree headings (315, 60, 300, 120 and 270 degrees for their fixture directions), rather than the stale non-multiple expectations from the old test.
- Split-mode clicks grab the test window's focus and send explicit motion/button coordinates after the long geometry checks, so they don't use a cursor left over another window.

### `selftest undo <folder> [--mode new|props|ui|split|load|drag|dropdown]` (`tests/Undo/UndoSelfTest.cs`)

Writes `undo_selftest.log` and restores `LastCity`.

| Mode | City | Notes / baseline |
|---|---|---|
| `new` (default) | creates one | 198 passing checks, 0 failures. The default fixture is now 2048 m, as in split mode: a 512 m fixture put the bumpy-terrain edit outside the heightmap and caused cascading history failures |
| `split` | creates one | 0 failures, ~50 s. **Must run windowed.** `SplitModeTest` is flaky on window geometry, so rerun once before blaming a change |
| `drag` | creates one | numeric field middle-drag, 0 failures, ~15 s. Captures the real mouse, so a moving mouse can fail the Shift check; rerun once |
| `dropdown` | creates one | dropdown keys/wheel, 0 failures, ~10 s |
| `height` | creates one | placement height (Shift + mouse movement), hidden terrain placement and snapping toggle, 30 OK, 0 failures, ~20 s. **Must run windowed.** Moves the real mouse, so rerun once before blaming a change |
| `guide` | creates one | the guides (`UndoSelfTestGuide.cs`): Markdown parser, **all the guides of the installed cores** (chapters, links, images), refused links, panel navigation, move/resize/minimize, input. 142 OK, 0 failures, ~10 s. **Must run windowed.** Moves the real mouse. Saves frames in `guide_fixtures` next to the log: look at them after a change to the renderer, the checks can't see the layout |
| `ui`, `load`, `props` | **a copy** of an existing city | the old test city is gone; use a copy of the api self-test city (`<scratch>/api/city`) or ask the maintainer for one |

Load/ui modes catch bugs that the scratch city misses. Reproduce user-reported bugs on a copy of a real city.

Simulating input in self-tests:

- `Input.ActionPress` does **not** work for clicks (the await continuations run after `_Process`), and `InputEventAction` counts as consumed by the UI. Use `WarpMouse` + `Input.ParseInputEvent(new InputEventMouseButton { ButtonIndex = Left, Pressed = true, Position/GlobalPosition = mouse })`, then release.
- Terrain modifiers need `Input.ActionPress("Select")` to apply.
- Panel buttons: reflection on `EditorPanelElements.Button`'s private `button`, then `EmitSignal(Pressed)` (goes through the undo recording). Reflection doesn't find a base class's private fields through the derived type, so use `typeof(Base).GetField`.
- Panels may be rebuilt when an element is selected: read panel fields after `SelectObject`.
- A test that deletes elements must call `M.FlagAsChanged()` like the editor does.
- Compare positions with a tolerance (projection drift).
- Editor key commands are polled globally (`GameEngine.Input`). Block them while a popup is open (`UIDetection.PopupOpen()`).

