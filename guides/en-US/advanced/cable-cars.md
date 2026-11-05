# Cable cars

## Making a line

1. Check **Cable car line** in the **Traffic** tab of each road of the line. Each road gets a rail in each direction, shown as orange traffic lanes.
2. Set **Cable car rails dist.** if needed. As in San Francisco, the rails are 2.5 m from the center of the road by default.
3. Connect the roads of the line through intersections.

## Where the cable cars go

The game puts one cable car, `va_cablecar_f`, at each **end** of a line. An end is an intersection where exactly one cable car road arrives, like the 4 ends of the San Francisco lines.

A line that is only a closed loop has no ends, so it gets no cable cars. Leave it open, or add a short cable car road from the loop to a dead end. The export log warns about lines without ends.

## Visible rails

The cable car lanes don't draw any rails: those are [decals](decals.md), which you place separately along the roads.

To join the rails across an intersection, click **Generate rail decals** in its panel, which works when at least two connected tram roads arrive there:

- It pairs the most opposite roads first, within a limit on the turn angle.
- It creates editable decals across the intersection only, with `r4i_rails_f`, 2 m wide.
- It adds a new set each time you use it, so delete the old decals by hand before generating them again.
