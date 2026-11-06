# Train splines and boat paths

Read the [repository instructions](../../AGENTS.md) first. Paths and command examples below are relative to this repository root unless another working directory is specified. Builder CLI and self-test commands run from the builder root.

Also read [Exporter workflow and engine limits](exporting.md) for shared limits and PATHSET flags. For movable decks and their controls, read [Bridges](bridges.md).

## Stock data

**Stock data:** SF cable cars are BAI `nTrams` = 1 on both sides, with the rail 2.5 m from the centre line. London's visible trains are `gizTrain` gizmos from `race/london/london_train.pathset`. Stock cities are compressed about 0.3-0.5x relative to real scale.

## Train splines

`elements/customElements/train` uses the shared core curve registry (`splineTypes.json`, ID 3, `mm2Train`), allowed only by that type. Roads and decals retain their own allowlists. `lua/trains.lua` reproduces train Hermite X/Z, fixed 0.5 tangents, wrapped neighbor lookup and linear Y. Export the authored `points.spline`, never evaluated sections. Empty/two-point paths remain editable but cannot be exported as moving trains. Import retains incomplete type-2 paths with warnings. No original stock data belongs in fixtures.

Reference executable SHA256: `992c53c9250cf822b44bf4a4013bd5805229bbbeb7b478a4c2556531bc5340f3`. `57A530` builds tangents, `57A370` evaluates Hermite, `57A6D0`/`57A710` wrap neighbors; `578A61..578A9F` override train Y. Comparing 295 positions from London's eight stock routes uses isolated emulation, not game execution. The static route preview does not model reversal timing or body/room/model offsets.

Migration 4 converts `cityProperties.trainLines`, preserving incomplete routes, existing IDs and unrelated data through the normal versioned backup mechanism. New templates use coreVersion 4 in `templates/_common/preferences.json`. Focused checks: `python exporters/psdl/tools/_test_trains.py`; builder integration: `KM2_SELFTEST_FOCUS=trains` with `selftest api <new folder>`. The integration also tests a temporary synthetic road curve and its split/merge callbacks, restoring the core registry and removing its test module/type in a finally block. An optional `KM2_TRAIN_REFERENCE` points to scratch JSON with native-coordinate points and emulated `{t,position}` samples; never commit it.

## Boat paths (boats, ducks, ferry)

`elements/customElements/boat` (one type; the `model` enum and `speed` float, curve ID 4 `mm2Boat`, `lua/boats.lua`, `spline.closed`) exports `race/<city>/<city>_sailboat.pathset` and `<city>_ferry.pathset` with `exporters/psdl/boat_export.py` (called next to `export_trains` under the `pathset` flag; both share `route_pathset.write_routes`). Export the authored `points.spline` (X mirrored), at least three points, room 0, type 2. Checks: `python exporters/psdl/tools/_test_boats.py`; builder `KM2_SELFTEST_FOCUS=boats` with `selftest api <new folder>` (also covers the generic `closed` spline setting). There is no importer for these paths and no race variants (`<city>_sailboat_<racetype>_<n>.pathset`, tried first by the game).

Reverse-engineered from the same executable as the trains (SHA256 `992c53c9250cf822b44bf4a4013bd5805229bbbeb7b478a4c2556531bc5340f3`), not run in game:

- Managers are created at `413210`: `(default model, name)` = (`giz_sailboat01_f`, `sailboat`), (`giz_bridge01_l`, `bridge`), (`va_ug_l`, `train`), (`giz_carferry01_f`, `ferry`), (`giz_pcar`, `parkedcar`). The sailboat loader `415240` and the ferry loader `415780` read `race\<city>\<city>_<name>[_<race type>_<race number>].pathset` (variant first, then without the suffix) with `467210` (PTH1: count, current path; per path a name32, point count, one unknown uint32, points of room uint32 + x, y, z, then type, spacing and 2 padding bytes; `466bd0` stores spacing / 4 at path+0x34).
- Model: for each path `geometry/<path name>.pkg` is used if the file exists (`4c59e0`), otherwise the default model of the manager (so `PATHn` is a sailboat). Stock names: `giz_sailboard01_f`, `giz_duck_s`, `giz_tug01_l`, `giz_watertaxi01_l`, `giz_carferry01_l`. There is no model-specific code in the sailboat manager: ducks and boats differ only in model, spacing and path.
- Movement: the sailboat objects (`578410`) use the train follower (`57A050`/`57A410`: `57A530` tangents = 0.5 x half-differences, `57A370` cubic on X, Y and Z, no Y override), advanced by a fixed 1/60 s per update, with speed constant along each span. The segment index wraps (`57A6D0`/`57A710`) and nothing stops it, so every route is a closed loop. The room is recomputed from the position (`465480`), so the room field of the points is unused (the stock files have real ones).
- Speed of the sailboat manager (`578707`): random in [spacing / 4 - 1, spacing / 4 + 1] m/s per object (stock: ducks 8 = 2 m/s, boats and tugs 20 = 5 m/s, sailboards 80 and 120 = 20 and 30 m/s). The ferry manager (`579910`) randomises `0.75 +- 0` for every path, so the spacing is not read (stock 20); in game it is still to be checked. The parked cars are not moving objects (see the **Parked cars** paragraph in [Native prop and INST reference](props-and-parked-cars.md#native-prop-and-inst-reference)).
- Open: the unknown per-path uint32 (29 in the SF ferry, 3 in one London duck path), the type-1 "directed points" paths of London's ferry, the room-height Y offset added by the ferry/train update (`5794d0`/`578aad`) that the sailboat update lacks, and exact moving collision/traffic behavior of bridges (see [Bridges](bridges.md)).
