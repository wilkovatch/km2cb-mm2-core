# PSDL custom elements and BAI

Read the [repository instructions](../../AGENTS.md) first. Paths and command examples below are relative to this repository root unless another working directory is specified. Builder CLI and self-test commands run from the builder root.

Also read [Exporter workflow and engine limits](exporting.md). Stock tram/train facts are in [Trains and boats](trains-and-boats.md#stock-data); texture conventions are in [Decals, textures and maps](decals-textures-and-maps.md#native-texture-reference).

## Custom elements

Most MM2 custom elements are the PSDL attributes, the others are the decals and trains (the generic mechanism is in the builder's `wiki/Core-Custom-Elements.md`, the decals and trains in the advanced guide). Equivalence check: export, convert everything, export again, compare PSDL room by room and BAI. The expected result is 0 differences.

### PSDL attributes

The PSDL attributes are for testing, so the README doesn't document them. They are `creatable: false` (no Create menu entry) and the `ui.json` of the `psdl` types has no `convert:toPsdl` button: they are made by the `toPsdl` converter (API `elements.convert`), the importer (`Scripts → Import MM2 city`) and `customElement.create`.

- Roads, intersections, terrain patches and building lines of type `psdl` (not exported to PKG) can be converted to the PSDL attributes they are exported to (converter `toPsdl`, run with the scripting API `elements.convert`), to edit them one by one: each vertex of the PSDL is a control point. Converting doesn't change the export: the converter runs the exporter on the element and turns the parts it would write into the attributes.
- The attributes are in rooms (one per PSDL room of the element); the parts of a building are in a group placed in the room where the building is when exported (Scripts > Assign building parts to rooms merges them into their rooms). The roads and intersections also get their BAI road or intersection, which can be edited too (lanes, rules, connections).
- A converted room gets its perimeter as the exporter follows it (with `simplifyPerimeter`). Since it is set, changing the shape of its contents (e.g. adding sections to a road) needs the perimeter to be computed again (Compute the perimeter from the contents, in the panel of the room) or removed.
- The BAI road of a converted road is Auto-calculated: when the road attributes converted with it are edited, its edges and curbs follow theirs (chained from room to room) and its lanes (as many as there are) are spread evenly between each curb and the middle of the road (or the dividers), as the exporter does when the lanes drawn in the editor can't be used. Its points can't be edited while it's on: uncheck Auto-calculated to edit them (the road attributes are then edited alone).
- The points of a converted building follow each other: the points above another one are on its vertical line, and the lowest points inside the top or bottom edge of a sliver or facade bound (the corners of the facades between the ends of a side) are on that edge, so moving a corner keeps the building together.
- A converted road gets the psdl props containers of its prop rule (the ghost keeps exporting the others).
- The converted roads and intersections stay as hidden ghosts, so that the other elements keep their shape; the panel of an attribute can bring the original element back.
- The `psdl` road type gives its intersections an anchor across each of its ends (`endAnchors`: the outer sidewalk edges, the curbs at road level and, with a divider, its sides), so all the points of the end section of a converted road stay on a procedural intersection and follow it.
- The dividers at the ends of a converted divided road follow the line between the curbs there (which it shares with the converted intersection), so they keep their places across the road when the intersection, or its room, is moved.
- Triangle fans, road triangle fans and roof triangle fans can be converted to each other. Road and roof fans keep all their vertices at the same height, facades stay vertical rectangles, the tops of facade bounds and slivers stay horizontal.
- The texture references are not elements: the exporter makes them from the textures of the attributes.
- The types are the attributes of the rooms of the PSDL (see the [file format](https://github.com/Dummiesman/angel-file-formats/blob/master/Midtown%20Madness%202/Room_attributes.md)) and the BAI elements; the control points are the vertices of the PSDL, the heights of the PSDL (facades, roofs, slivers) come from the positions of the points when exported:

  | Type | Attribute | Points |
  |---|---|---|
  | `room` | A room of the PSDL: contains the attributes and the BAI elements. Echo, warp, hudmap category. Its `perimeter` (a closed array, drawn as a magenta line that can be clicked to select the room) is written as it is, in the order of its points, the neighbours being the rooms sharing its points (their attributes or perimeter); with `simplifyPerimeter` the points in a straight line that lead to no other room are left out, and the spikes, as for the perimeter the exporter finds when it has none (fewer than 3 points). The button *Compute the perimeter from the contents* (converter `roomPerimeter`) sets it to the one the exporter would find, with `simplifyPerimeter`. | `perimeter` |
  | `buildingGroup` | The parts of a building outside of a room: they go in the room found at `location` (or at `frontLocation` if there is none there), as the procedural buildings. The core script Assign building parts to rooms merges every group into its room. | `location`, `frontLocation` |
  | `roadWithSidewalks` | 0x00; props containers `right` and `left` (along the sidewalks) | `sections`: `leftSidewalk`, `leftRoad`, `rightRoad`, `rightSidewalk` |
  | `roadWithoutSidewalks` | 0x02 (or 0x00 without sidewalks) | `sections`: `left`, `right` |
  | `dividedRoad` | 0x08: the divider drawn as the procedural roads (flat: a strip whose texture repeats `dividerValue` times across it; elevated: `dividerValue` high, its top edges beveled by as much; wedged: 1 m high, 0.5 m narrower on each side at the top), the closed ends with the cap texture; props containers `right`, `left` and `middle` (on the flat and elevated dividers) | `sections`: `leftSidewalk`, `leftRoad`, `leftDivider`, `rightDivider`, `rightRoad`, `rightSidewalk` |
  | `roadTunnel` | 0x09 (subtype 3), before the road attribute of its `road` parameter | - |
  | `junctionTunnel` | 0x09 (subtype 0): walls on the edges of the perimeter of the room between consecutive points | `walls`: `points` |
  | `sidewalkStrip` | 0x01 | `sections`: `inner`, `outer` |
  | `sidewalkCap` | 0x01 end piece | `a`, `b` |
  | `crosswalk` | 0x04 | `p1` to `p4` (in the order of the PSDL) |
  | `triangleFan`, `roadTriangleFan`, `roofTriangleFan` | 0x06, 0x05 (written as 0x06 if not flat), 0x0c: the whole mesh, split in fans when exported. The road and roof fans keep all their vertices at the same height. | mesh |
  | `facade` | 0x0b, after its facade bound (`bound` parameter); a vertical rectangle | `bottomLeft`, `bottomRight`, `topLeft`, `topRight` |
  | `facadeBound` | 0x07 (`bothSides`: also in the room in front of it); the top edge horizontal, the bottom one can be slanted | the same |
  | `sliver` | 0x03; as the facade bounds | the same |
  | `baiRoad` | A road of the BAI: its lanes (the arrays are uniform), its intersections (a BAI intersection, or a procedural intersection: the BAI intersection replacing it if it is a ghost, otherwise the procedural intersection lists it among its roads, in their order around it), rules, pedestrians... `autoCalculated`: see above (`psdl.baiRoadPoints`). | `sections`: `rightEdge`, `rightCurb`, `backwardLanes`, `forwardLanes`, `leftCurb`, `leftEdge` |
  | `baiIntersection` | An intersection of the BAI, in its room: its roads are the BAI roads ending on it (and the procedural roads ending on the intersection it replaces), counterclockwise | `center` |

## BAI and pedestrians

**Pedestrians (BAI sidewalks):** the walk target is evaluated 6 m ahead on an **unclamped** Hermite curve, so short sidewalk segments that turn make pedestrians fly off and circle. Segments touching a sharp corner need to be ≥ ~16 m. `bai_writer.spread_corner_points` moves only the sidewalk points; the 2 m car sections stay.

**BAI:** coordinates are (x, up, z) with x mirrored. The engine's room lookup returns the first intersection of a room before its roads, so don't put extra intersections in road rooms. For stock BAI derivation rules see the maintainer's psdl-viewer project, `Scripts/Formats/BaiFile.cs` (location in the builder's `CLAUDE.local.md`).
