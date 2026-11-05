# Trains and boats in depth

## Trains

Each train is its own element, using the path behavior of the London trains. The model is chosen by the game, and train paths have no presets.

- **The preview:** the yellow line shows the game's own curve, from the second point to the second-last one, where the train stops. It is raised 0.25 m in the editor to stay visible, but the export isn't affected. The preview is static: it shows the route, not the movement or timing.
- **The curve:** the shape on the ground is a curve with no editable tension, but the height is a straight line between each pair of points.
- **Export:** the points you placed go to `race/<city>/<city>_train.pathset`. With no valid route, an old file there is removed.
- **Heights:** points keep the height you give them, with no projection on the surface. The stock London trains run about 13 m below the streets.

No train, track or tunnel mesh is generated. Place the tunnels and stations as meshes on invisible terrain patches, such as the stock `bl_subway*`, `cl_subway*`, `kl_subway*`, `ol_subway*` and `wl_subway*`.

While you draw, the placement reference is yellow: the last point when adding at the end, the first when adding at the start, or the selected one when inserting.

## Boats

Each route is a closed loop, moving forever. Click the first point to finish it.

| **Model** | Default speed | Written to |
|---|---|---|
| **Sailboat** | 5 m/s | `<city>_sailboat.pathset` |
| **Sailboard** | 20 m/s | `<city>_sailboat.pathset` |
| **Duck** | 2 m/s | `<city>_sailboat.pathset` |
| **Tug** | 5 m/s | `<city>_sailboat.pathset` |
| **Water taxi** | 5 m/s | `<city>_sailboat.pathset` |
| **Car ferry** | Fixed | `<city>_ferry.pathset` |

Both files are in `race/<city>/`. In the game each boat varies by 1 m/s around its speed, and **the car ferry ignores the speed**.

The cyan line shows the game's own curve, through the points in all three axes. So the height of the points is the height of the boat, and no model is generated in the editor.

Not supported:

- Routes specific to a race
- Bridges
- Importing the routes of existing cities

## Arrows

Traffic lanes, boat routes and opponent routes show arrows for their direction. Train lines don't, because trains run back and forth, and neither do pedestrian lanes. Arrows are only for the editor.
