# Parked cars

Parked cars are placed by the game, not by you: you only say where the slots are. The cars in the editor are an example.

## The ways to place them

- **Parked cars** as the props type in the **Props** tab of a road, for example in its parking row.
- **Parked cars** as the type of a **Prop line**.
- **Create → Props → Parked car** for a single slot.

## What the game decides

For each slot, the game chooses the car, its color, or nothing at all.

| | Models | Empty slots | Traffic density |
|---|---|---|---|
| Stock MM2 | `giz_pcar01_l`, `giz_pcar02_l` | 1 in 3 | No effect |
| MM2Hook defaults | The same, plus `giz_pcar03_l` | 1 in 4 | In Cruise mode, removes parked cars |

With MM2Hook's defaults, there are no parked cars at all in Cruise mode when there is no traffic.

The layout stays the same from one launch to the next, but editing the city can change it. To have a specific car in a specific place, use a normal prop.

Turn on **Assume using MM2Hook** to include the third model in the examples. The exported files are the same either way.

## Settings

- **Slot distance** goes from 5.25 to 100 m. The third model is 5.49 m long, so it overlaps at the shortest distances.
- **Reverse direction** turns a row around.
- The cars of a road row follow the traffic of the nearest lanes, so **Left-hand traffic** turns them around too.
- On a prop line, the cars run against the direction of the spline, whichever side the traffic drives on.

## Details

- **Slopes:** the game rolls the cars sideways instead of tilting them along the road, while the editor shows them level. The export warns above 5 degrees, so keep parked cars on nearly flat streets.
- **Single slots** can't be scaled, pitched or rolled. They keep their height until you move them or use **Project to ground** again.

## Files

Parked cars go in `race/<city>/<city>_parkedcar.pathset`.

A prop line that belongs to a race goes in `<city>_parkedcar_<race>.pathset`, together with the rows of the rest of the city, because in that race the game reads that file instead of the main one.

A file holds at most 192 rows, and each single slot uses one. The export reports an error above that and writes the first 192, with the rows of the race first.
