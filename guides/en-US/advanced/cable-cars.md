# Cable cars

## Making a line

1. Check **Cable car line** in the **Traffic** tab of each road of the line. Each road gets a rail in each direction, shown as orange traffic lanes.
2. Set **Cable car rails dist.** if needed. As in San Francisco, the rails are 2.5 m from the center of the road by default.
3. Connect the roads of the line through intersections.

## Where the cable cars go

The game puts one cable car, `va_cablecar_f`, at each **end** of a line. An end is an intersection where exactly one cable car road arrives, like the 4 ends of the San Francisco lines.

A line that is only a closed loop has no ends, so it gets no cable cars. Leave it open, or add a short cable car road from the loop to a dead end. The export log warns about lines without ends.

## Where the cable cars turn

At the end of a road a cable car goes on into the next cable car road of the intersection:

- With **2** cable car roads, into the other one, whatever the angle between them.
- With **4**, into the opposite one (the second cable car road after its own, going around the intersection), so two lines can cross.
- With **3**, or more than 4, it can't go on: it jumps back to the start of its own road. The export log warns about these intersections.

It leaves its road a little before the end (half the length of the car, 4.36 m) and crosses the intersection along a wide curve.

## Visible rails

The cable car lanes are not drawn in the game: the rails are [decals](decals.md), which the roads and the intersections can draw for you.

- On a road, check **Rail decals** in its **Traffic** tab (with **Cable car line**) to draw both rails along it.
- On an intersection, check **Cable car rails** in its **Rails** tab (with 2 or 4 cable car roads) to draw the rails across it, along the path the cars take in the game. The rails arriving there from roads with rail decals then stop where the cars leave the road, so that they join the curves.
- Where two rails cross, the intersection adds a square crossing decal (`r4i_railsX_f`); check **No rail crossings** to leave them out.
- **Rail texture** (`texture/r4i_rails_f.tex` if empty), **Rail decal width** (2 m if empty) and **Rail crossing texture** (`texture/r4i_railsX_f.tex` if empty) change the look.

These decals follow the roads and intersections when you edit them, and they can't be selected or edited on their own. For different rails, leave the options off and place [decals](decals.md) by hand.
