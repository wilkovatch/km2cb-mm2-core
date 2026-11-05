# Low LOD textures

At its lowest level of detail, the game draws a road with a single texture, which shows the sidewalks, the road and the divider in proportion to their widths. So a stock texture such as `r6_lo_f` only looks right on roads of about the same widths.

## Generating one

Click **Generate low LOD texture**, below the textures in the **Main** tab of a road. It:

- reads the road, sidewalk and divider textures and widths of the road
- writes `texture/<road texture>_lod_<hash>.tex` in the city folder
- sets it as the **Low LOD texture** of the road

The button is enabled on **Double** roads with a road texture, because the other roads have no low LOD texture in the PSDL.

## Things to know

- **It doesn't update by itself.** Generate it again after changing the textures or widths.
- **Equal results share one file,** and each new file counts towards the limit of textures of a city.
- **Undo restores the old texture of the road, but the file stays.** It is packed into the `.ar` with the rest of the folder, so delete the ones you no longer use by hand.
- **`_fa` versions:** when the road texture has a `_fa` version, as the stock ones do, one is written for the low LOD texture too.

With **MM2 archive (.ar)** the texture goes with the city. Otherwise, copy it like any other custom texture, from the `texture` folder of the city to the one of the game.
