# Props and meshes

Everything that isn't a road, terrain or a building line is placed from the **Create** menu.

## Choosing the right type

| Create entry | What it is | In the game |
|---|---|---|
| **INST mesh** | A static model, such as a landmark | Part of the city |
| **Props → Individual prop** | A single object, such as a mailbox | A prop, which can usually be knocked over |
| **Props → Prop line** | A row of props along a line | Props, or a native path |
| **Props → Polygon** | Props scattered in an area | Individual props |
| **Props → Parked car** | One parking slot | A parked car |

The difference between an INST mesh and an individual prop can't be changed later, so pick one before placing it.

## Placing a mesh

1. Select the type in **Create**.
2. Pick a mesh from the list (you can search by name), and click **Start placement**.
3. Click on the ground. To set its heading, keep the button held and drag.
4. Press Escape when you are done.

Click a placed mesh to edit it: W moves, E rotates, R scales.

> The game doesn't support scaling props. It only supports horizontal scaling of INST meshes visible from all angles, and their collision doesn't scale with them.

## INST meshes need a block

An INST mesh goes in the block under it, so it must stand on something that becomes a block. An invisible terrain patch works. Otherwise it is not exported.

The game can only load about 600 different objects in the INST file. The same mesh used many times counts once, so reuse meshes. The exporter warns above 597.

## Props along roads

You don't have to place every lamp post by hand. In the **Props** tab of a road, choose **Edit left**, **Edit right** and so on, to set what grows along that part of the road.

When the type is **PSDL prop rule** on the left or right side of a road, it is exported as a real prop rule of the game. Everything else is exported as individual props. The [Advanced guide](../advanced/props.md) compares the types.

## Parked cars

Set the props type to **Parked cars** in the **Props** tab of a road, or use a **Prop line**. The parking lanes of the road are a good place for them.

The cars you see in the editor are only an example: **the game decides** which slots are used, and which cars and colors they get. For a specific car in a specific place, use a normal prop.

A file can hold at most 192 rows, and the export reports an error above this.

## Custom props

The game draws most props based on data in `tune/banger`, and the editor uses the same data to show them correctly: this comes with the imported assets. A prop with no such data sits with its lowest point on the ground.
