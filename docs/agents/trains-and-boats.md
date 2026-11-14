# Train splines and boat paths

Read the [repository instructions](../../AGENTS.md) first. Paths and command examples below are relative to this repository root unless another working directory is specified. Builder CLI and self-test commands run from the builder root.

Also read [Exporter workflow and engine limits](exporting.md) for shared limits and PATHSET flags. For movable decks and their controls, read [Bridges](bridges.md).

## Stock data

**Stock data:** SF cable cars are BAI `nTrams` = 1 on both sides, with the rail 2.5 m from the centre line. London's visible trains are `gizTrain` gizmos from `race/london/london_train.pathset`. Stock cities are compressed about 0.3-0.5x relative to real scale.

## Cable cars

Reverse-engineered from the same executable as the trains (SHA256 `992c53c9…`), not run in game. `traffic/rails.py` emulates it and `lua/cableCars.lua` draws the intersection rails with the same rules.

- `aiMap::Init` (`5359d6`) creates one `va_cablecar_f` object (0x184 bytes, vtable `5b5604`, init `53f7e0`) on each intersection where exactly one road has trams (`54a220`). A road has trams when its second side in the file (aiPath +0xDC, the BAI left side, start to end) has tram vertices (`549980`).
- Movement (update `53fbd0`, advance `540bf0`): the car follows the tram vertices of its side, one segment at a time, along a 2D (x, z) cubic Hermite (`558990`, standard basis set up at `556d50`), with the BAI centre tangents times the centre distance of the segment (`548ad0`, `547340`). The parameter is distance / segment length. The car's position is the curve point; its height comes from elsewhere.
- **Next road** (`53fcd0`): at the end of its road the car counts the roads of the intersection with trams:
  - **1**: the end of a line; it takes the same road in the other direction (a U-turn loop curve).
  - **2**: the other one.
  - **4**: the second road with trams after its own, in the order of the intersection (the opposite road of a crossing).
  - **3 or more than 4**: none. The "next" road stays its own, so after the curve it starts its own road again, jumping back across it. The exporter warns about these intersections.

  The direction on the next road is the one going away from the intersection.
- **Through the intersection** (rail type 1): the curve is a Hermite in x and z with these points and tangents:
  - **Start:** the start is on the last segment of the rail at the fraction (L − h) / L, where L is the last centre segment length (`cdist[n-1] - cdist[n-2]`, for both directions) and h = 4.36 m. h is −min z of the cable car bounding box (`+0x4c`, BODY_H/M): the car leaves its road half its length before the end.
  - **End:** the end is the first tram vertex of the next road's side.
  - **Tangents:** the tangents are the road directions (−Z of the last section and −Z of the first, `548cc0`/`548d50`), scaled by the Manhattan distance |dx| + |dz| between start and end.

  The scale is wider than a circle arc in a turn: a 90° turn of 10 m passes at (2.5, 7.5) instead of (2.93, 7.07).
- **Check against the stock data:** `python -I exporters/psdl/tools/cable_car_rails_check.py [--sample N] sf.bai sf/decals.pathset` compares the emulation with the stock `r4i_rails_f` decals (`_test_cable_car_rails.py` holds the synthetic checks):
  - On the straight crossings it matches within about 0.1 m.
  - On the four 90° turns (intersections 61, 62, 69, 115) it is 1–3 m off, and so is every variant of the tangent scale and start point. Those stock decals were drawn by hand and don't follow the cars.
  - The stock rail decals start at the road ends (the road rails are in the road textures), and the stock line ends have no loop decals.

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
