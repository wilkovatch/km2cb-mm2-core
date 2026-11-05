# Trains and boats

Things that move by themselves are in **Create → Moving objects**.

## Cable cars

Cable cars aren't placed here: they are part of the roads. Check **Cable car line** in the **Traffic** tab of each road of the line, and connect those roads through intersections.

The game puts one cable car at each end of a line. **A closed loop has no ends, so it gets no cable cars**: leave the line open.

## Trains

Choose **Create → Moving objects → Train** and place points along its route. The train goes back and forth like the London trains. The game chooses the model.

- The train runs from the **second** point to the **second-last** point. The outermost points only shape the curve. A yellow line shows the real route.
- A route needs at least 3 points to be exported, and 4 to show the yellow line.
- Tunnels and stations aren't generated: place them as meshes, for example the stock London `bl_subway` meshes, on invisible terrain patches. The stock trains run about 13 m below the streets.

## Boats, ducks and ferries

Choose **Create → Moving objects → Other moving object** and place the route of one boat. A route is always a **closed loop**: the last point connects back to the first. It needs at least 3 points.

- **Model** can be a sailboat, sailboard, duck, tug, water taxi or car ferry.
- **Speed (m/s)** sets the speed. 0 uses the default of the model.
- The points keep the height you give them, which is the height of the boat. Stock boats are at -2 m, the level of the water.

A cyan line shows the path the game will follow.

## Movable bridges

Choose **Create > Moving objects > Movable bridge**, click the first hinge, then the opposite one, at the same height. Click the cyan point on a free road end to attach a hinge to it. To place them again, choose **Click mode > Place the points one by one**. Then choose a **Model**, or attach the controls to road ends and press **Generate model from the roads** to get one made for them. Turn **Paired leaves** off for one leaf. The bridge keeps its model size.

Choose **Timed**, **Proximity**, **Closed** or **Open** behavior. **Preview pose** lets you inspect the closed or open bridge without changing that behavior. Place the approaches and supports separately, with no static road deck in the opening. See [Trains and boats in depth](../advanced/trains-and-boats.md) for the native limits and bridges specific to a race.
