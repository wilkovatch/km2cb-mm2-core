# Roads

Draw roads with **Create → Road** (Ctrl+R). There are two road types:

- **PSDL compatible** is the normal one, exported as the game's own road geometry.
- **Dummy** has fewer tabs, and isn't written as PSDL road geometry. You rarely need it.

The panel of a **PSDL compatible** road has these tabs:

| Tab | What it sets |
|---|---|
| **Main** | Widths, sidewalks, textures, and export options |
| **Inters.** | Crosswalks and how the road meets its intersections |
| **Traffic** | Lanes, parking, traffic rules and traffic lights |
| **Divider** | The divider down the middle of the road |
| **Props** | Things placed along the road |
| **Railing** | Railings, walls and galleries |

## Widths and textures

In **Main**, set **Total width** and **Road width**: the difference between them is the room for the sidewalks. Then choose the **Road texture** and **Sidewalk texture** in the same tab.

The sidewalks of the game are always 15 cm high.

## Lanes

In the **Traffic** tab, set **Forward lanes** and **Backward lanes**. The game supports at most **4 lanes per side**: extra lanes are dropped, with a warning in the export log.

Other useful settings there:

- **Forward parking lane** and **Backward parking lane** keep room at the edge of the road, where traffic doesn't drive.
- **Pedestrians only** makes the road an alley.
- **Disable traffic** keeps ambient vehicles off the road.
- **Freeway** makes ambient vehicles go faster.
- **Behavior at start intersection** and **Behavior at end intersection** say whether vehicles stop there, or use traffic lights.

To see the lanes of every road, with arrows showing their direction, turn on **View → Show all traffic lanes**.

## Curves and hills

A section of a road has to be flat, because the collision of the road in the game is made of flat four-sided pieces. A road that curves left or right *and* goes up or down at the same time can't always follow this.

**Make coplanar** adjusts these roads to keep their sections flat, and it is on by default. It works well for gentle curves on a slope, but on tighter ones the result can look ugly, so keep them gentle.

## Two roads on top of each other

Check **Add warp** on a road that lies on top of another one, for example on a bridge. The same tab has **Add echo**, which adds an echo to the sound on a gallery or underground road.

## Pedestrians

Pedestrians walk along the sidewalks, and can behave strangely on short curved stretches. The [Advanced guide](../advanced/traffic.md) explains why.
