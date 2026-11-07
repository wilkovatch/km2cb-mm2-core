# Traffic and pedestrians

Ambient vehicles, pedestrians and cable cars follow the paths shown in the editor (the traffic lanes, the paths on the sidewalks and the cable car rails), and the exporter writes them to the BAI file. Lane spaces, parking spaces and different numbers of lanes per side are all kept in the game.

## Road settings

In the **Traffic** tab of a road:

- At most 4 lanes per side work in the game. Extra lanes are dropped, with a warning.
- **Pedestrians only** makes it an alley.
- **Freeway** makes ambient vehicles go faster.
- **No pedestrians on right side** and **No pedestrians on left side** remove the pedestrians from one side.

Level roads get the flat flag of the BAI file by themselves.

## BAI-only roads

A road of type **BAI-only road** has no geometry: only its traffic lanes and pedestrian paths, exported to the BAI file. Use it where the ground is made by something else, such as terrain patches or meshes exported to PKG, and you still want ambient traffic there.

- It has the **Traffic** tab of the PSDL roads, and the widths that place the lanes: total width, road width, sidewalks (where the pedestrians walk), two-way and the divider.
- It is drawn as its line and its traffic lanes. Click the line to select it.
- At an intersection it doesn't change the surface of the other roads. An intersection where all the roads are BAI-only has no surface at all.
- In the BAI file it belongs to the rooms under it. Lay it over the surfaces of other elements. A BAI-only road or intersection that is over no room is left out of the BAI, with a warning.
- The game finds only the first intersection of a room. An intersection with only BAI-only roads that is in the room of another intersection gets a warning. Give each one a surface of its own under it, such as a small terrain patch.

## Intersections

- More than 11 roads at an intersection crash the game's traffic code. The exporter warns, and splits such an intersection into a ring of smaller ones for the traffic.
- In `mm2.log`, `Vehicle ... did not have permission to traverse intersection` means vehicles broke the **First in, first out** rule at an intersection. The stock San Francisco uses that rule only at ends with 3 roads.

## Pedestrians and short sidewalks

A pedestrian aims at a point 6 m ahead along the sidewalk. The game doesn't stop that point at the end of the curve it follows, so on a short stretch of sidewalk that turns, the target ends up far from the sidewalk. Pedestrians then fly off and circle around.

Stretches of sidewalk that touch a sharp corner should be at least about 16 m long. The exporter already spreads the points of the sidewalks around corners, but short curved roads with sidewalks can still show this.

## Checking the result

The tool `exporters/psdl/tools/bai_check.py` in the folder of the core compares a BAI file with the conventions of the stock files:

```
python bai_check.py --lint <file.bai>
python bai_check.py --derive <file.bai>
```

The first reports problems, including intersections with too many roads. The second recomputes the derived fields and reports the biggest difference.

The export option **Accurate BAI culling** is a slower, more exact version of a calculation in this file. See [Export options](../export/flags.md).
