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
- Importing the routes of existing cities

## Movable bridges

Choose **Create > Moving objects > Movable bridge**, then click the two hinges, one after the other: the first click creates the bridge, the second places the other control. Until then the first hinge is yellow, with a line to where the second would go, and closing the editor removes the unfinished bridge. With **Paired leaves** off, the first is the hinge and the second sets the direction. The models keep their original dimensions; moving the hinges apart does not stretch the deck.

A click on the cyan point on a free road end puts the hinge on it: the control follows that road end from then on. A click on an anchor along the road edges, or on another point, attaches it there too. **Click mode > Place the points one by one** places both controls again in the same way. A placed control can also be attached later: select it, press M, choose **Attach to point/anchor/segment** and click the target. Keep the hinges level.

**Model** can be any PKG, not only the stock `giz_bridge01_l` (30 m), `giz_waterloo_l` (23.18 m) and `giz_bridge02_l` (20 m). The leaf runs along the Z axis of the model, which should be centered on its origin, like `giz_bridge01_l`. In the game a bridge needs the banger data of its model, or it crashes: the file `tune/banger/<model>.dgBangerData` of the city is exported with the bridge, and without one the export writes a new one from the size of the model. The file name can have up to 23 characters for all the behaviors. A `bound/<model>_bound.bnd` file is optional: without it, the collision is a box of that size.

**Generate model from the roads** makes a model that fits the roads, once at least one control is on a road end. Its top is the cross section of the road, with the same widths, sidewalks, divider and textures, and each leaf reaches the middle of the two hinges (all the way with **Paired leaves** off). A road at an angle shears the leaf, so that its ends follow the end of the road. The sides, ends, bottom and railings are made like the stock bridges: **Side texture** is the truss on the sides and ends, also used for the bottom, **Bottom texture** is the plate under the road, seen through the truss, and **Railing texture** is the railings, in the middle band of the texture like the stock `tl_bridgetrim_l`. A texture you choose must be in the game or in the `texture` folder of the city.

The model, its collision and its banger data go in the city folder, and into the export. It doesn't follow later changes: generate it again after moving the hinges, changing the road or its textures, the textures above or **Paired leaves**. The export warns if the hinges moved. Each result is a new file, and the old ones stay in the folders (`bridge_...`), so that undo keeps working; delete the ones you no longer use by hand.

Both leaves of a pair always use one model, because the game draws the second one by turning the first by 180 degrees. If the two roads differ, the model fits the widest one, and the angle is the mean of their two angles.

**Behavior** is **Timed**, **Proximity**, **Closed** or **Open**. The game opens to 27 degrees, takes about 9.4 seconds to move, and waits 10 seconds. Proximity checks the player and opponents within 100 m. These are fixed game settings. **Preview pose** only shows a static pose in the editor. Import the game assets for the preview of the stock models; the cyan control line is available without them.

Create a bridge while a race is selected to put it in that race. **Replace city bridge (race only)** lets that bridge replace one city bridge for the race; the panel of a city bridge doesn't have it. Leave it empty to add another. While the race is selected, the city bridge it replaces is hidden. Every other city bridge is kept in the race file. Both amateur and professional use the same bridges.

Bridges export under **Export PATHSET**, separately from props and static meshes. Author the approaches, supports and surrounding rooms separately. Leave the moving deck clear of static road surfaces and collision. Traffic paths and signals are not generated. The editor does not simulate the movement, collision or traffic; those still need checking in the game.

## Arrows

Traffic lanes, boat routes and opponent routes show arrows for their direction. Train lines don't, because trains run back and forth, and neither do pedestrian lanes. Arrows are only for the editor.
