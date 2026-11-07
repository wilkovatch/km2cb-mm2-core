# Low LOD textures

At its lowest level of detail, the game draws a road with a single texture, which shows the sidewalks, the road and the divider in proportion to their widths. So a stock texture such as `r6_lo_f` only looks right on roads of about the same widths.

## Generating one

Check **Generate low LOD texture**, below the textures in the **Main** tab of a road. When the city is exported, the exporter:

- reads the road, sidewalk and divider textures and widths of the road
- writes `texture/<road texture>_lod_<hash>.tex` in the export
- uses it for the road, in place of its **Low LOD texture**

It works on **Double** roads with a road texture, because the other roads have no low LOD texture in the PSDL. A road preset keeps the flag, like the textures.

## Things to know

- **It follows the road.** Each export makes it from the current textures and widths, so there is nothing to generate again, and nothing is written in the city folder.
- **The editor doesn't show it,** as it doesn't show a low LOD texture chosen by hand: the game uses it only far away.
- **Equal results share one file,** and each different one counts towards the limit of textures of a city.
- **If a texture of the road is missing,** the export warns and the road keeps its **Low LOD texture**.
- **`_fa` versions:** when the road texture has a `_fa` version, as the stock ones do, one is written for the low LOD texture too.
- **Bridges:** a model generated for a movable bridge on the road uses it too, for its farthest level of detail.

With **MM2 archive (.ar)** the texture goes in the archive. A loose export writes it in the `texture` folder of the export. An export with both **Export PSDL** and **Export PATHSET** removes the generated files that are no longer needed (see [Where the files go](../export/layout.md)).
