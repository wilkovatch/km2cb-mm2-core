This core for km2 City Builder adds support for Midtown Madness 2 cities

The main repository for the city builder is here: https://github.com/wilkovatch/km2-city-builder

This core uses code from this repository: https://github.com/wilkovatch/psdl-exporter-common, it's included as a submodule, so make sure to use `--recurse-submodules` when cloning this repository.

To import the output in Blender you can use these two plugins:
- https://github.com/wilkovatch/km2cb-to-blender-mm2-plugin (to import the resulting .bin file in Blender)
- https://github.com/wilkovatch/mm2-blender-psdl-plugin (to export the PSDL and other files)

Exporters supported (accessible by selecting the PSDL format when exporting):
 - PSDL
 - BAI
 - INST
 - PATHSET (props and decals)
 - Prop rules
 - PKG and bounds (BND, BBND, TER) of the elements exported to PKG
 - BIN (select "BIN only" to save only the BIN file and use it in Blender)

Additional texture formats supported:
 - .tex

Additional mesh formats supported:
 - .pkg

Additional features:
- Railings
  - You can place railings on roads and terrain patches.
  - For roads, go to the Railing tab and just set the railing properties.  
The Continue checkboxes at the bottom of the tab control how they are placed on neighboring intersections.
  - For terrain patches, go to the Railing tab, click Add railing, set the properties, and select the perimeter points over which the railing has to be placed.  
  To do so: click Switch to railing placement, then click on the terrain patch perimeter points.  
  Make sure the perimeter points will be the actual block perimeter points, otherwise it will not work properly ingame. (as railings are placed on the perimeter points of the block, not of the terrain patch)

- AI paths (BAI)
  - Ambient vehicles follow the traffic lanes shown in the editor, so the lane spaces, the parking spaces and different numbers of lanes per side are kept ingame. The BAI fields are computed as in the stock San Francisco and London files (route points 15 m from each end, lane boundaries, sidewalk distances, flags, etc.).
  - At most 4 lanes per side are supported by MM2, extra lanes are dropped with a warning in the export log.
  - The road flags come from the Traffic tab of the road: Divided road, Pedestrians only (alley) and Freeway (ambient vehicles go faster). Level roads get the flat flag automatically.
  - `exporters/psdl/tools/bai_check.py` checks a BAI file (stock or exported) against the stock conventions: `python bai_check.py --lint <file.bai>` reports problems, `--derive` recomputes the derived fields from the paths of the file and reports the maximum error.
- Cable cars
  - Check Cable car line in the Traffic tab of the roads of the line: they get a rail in each direction, shown in the editor as orange traffic lanes. As in San Francisco, the rails are 2.5 m from the center of the road by default (Cable car rails dist.).
  - Connect the roads of a line through intersections. The game puts one cable car (va_cablecar_f) at each end of a line, meaning each intersection where exactly one cable car road arrives, like the 4 ends of the San Francisco lines. A line that is only a closed loop has no ends, so it gets no cable cars: leave it open, or add a short cable car road from the loop to a dead end. The export log warns about lines without ends.
  - The rails are AI paths. To see them, check Cable car rail decals in the Decals tab of the city properties: each rail gets a decal (`r4i_rails_f`, 2 m wide, as in San Francisco, or the texture and width set there), going on through the intersections from a road of the line into the next one (the roads whose directions are more than 60 degrees apart; crossings of two lines get no crossing pieces). They are made by the exporter: the editor shows only the orange traffic lanes of the rails. Otherwise add them to the road texture or as props.
- Export to PKG
  - Check Export to PKG on a road, intersection, terrain patch or building line to export it as a mesh instead of PSDL geometry. It saves PSDL vertices and allows shapes that the PSDL can't have.
  - Roads, intersections and terrain patches still become blocks, but empty ones (with the perimeter of the element and no surface), and the element is placed in its block through the INST file. Building lines are placed in the block they are on, as usual.
  - The meshes are written to `<city>_geometry/<city>_mesh<n>.pkg` (low LOD only, used by the game at every distance) and their colliders to `<city>_bound/<city>_mesh<n>_BOUND.bnd/.bbnd/.ter`, next to the PSDL file: copy them into the `geometry` and `bound` folders of the game. The meshes are relative to the bottom center of their bounding box.
  - The materials of the colliders (the ground type, e.g. cobblestone or grass) come from the textures of the polygons, as in the PSDL, through the `city/materials.csv` file of the game: copy it to `Files/common/MidtownMadness2/city/materials.csv` (next to the `geometry` and `texture` folders of the game files), and add the custom textures to both copies. Without it, or for textures not in it, the colliders use the `default` material.
  - Uncheck Export PKG and bound files in the export dialog to write only the INST entries and the empty blocks (e.g. when the meshes didn't change). A collider can have at most 65535 vertices and polygons; the TER file at most 65535 polygon references (about 10 m cells), bigger ones are skipped with a warning.
- Trains
  - Add the lines in the Trains tab of the city properties. Each line is a train (va_ug_l, the London underground train) going back and forth between its first and last point, through the other points. Add the points with Switch click placement mode (then click on the terrain or on roads, Esc to stop) and move them like the other objects; they are joined by a line in the editor.
  - The lines are exported to `race/<city>/<city>_train.pathset`, as in London.
  - The tunnels and stations are not generated: place them as mesh instances, for example with the stock London meshes (`bl_subway*`, `cl_subway*`, `kl_subway*`, `ol_subway*`, `wl_subway*`) on invisible terrain patches (empty blocks), and put the points of the line inside them (the London trains run about 13 m below the streets).

- Decals
  - Textured strips lying on the roads or the ground, like the London zebra zigzags (`decal_zigzag_l`), yellow boxes (`decal_x_inter_l`) and the San Francisco cable car rails (`r4i_rails_f`). Add them in the Decals tab of the city properties: each decal has a texture, a width and a centre line; add its points with Switch click placement mode (then click on roads or the ground, Esc to stop) and move them like the other objects: they stay on the surface under them. The editor shows the decal as the game will; its points only show while it is being edited (opening it from the list selects it, the menu bar deselects it).
  - They are exported with the PATHSET, to `<city>/decals.pathset` (next to `props.pathset`), as the game reads it: each decal is a strip of the texture tiled along it in square tiles as wide as the strip, with a whole number of tiles in each piece. The texture must be in the game (it's not exported), its transparent parts show what's under the decal. Texture names can have at most 31 characters.
  - The game draws each piece of a decal (every segment, split every 25 m at most) only when the room (block) where it starts is visible: keep decals on the blocks, the export log warns about points outside of them.
  - `exporters/psdl/tools/decal_check.py` checks a decals.pathset file (stock or exported): the faces, the tiles and the names.

Some things to consider when creating cities:
- Changing of mesh instances scale in unsupported in MM2
- Mesh instances will be written to the INST file if not flagged as props (if flagged as props they will go in the PATHSET file)
- To make MM2-style buildings with no real ground floors, set the ground floor height to 0, this way only the top block will be used to make the sliver.
- Invisible terrain patches will generate empty blocks in MM2, which can contain other things. (INST buildings, PSDL buildings, etc.)
- In MM2 only horizontal scaling is supported for INST meshes visible from all angles. Furthermore, the collider will not be scaled if present.
- Road sections in MM2 must be coplanar, the MM2 template has the option to force this set. It only affects roads that bend both horizontally and vertically, but the result can be ugly for non-slight curves.
- Roads, intersections and terrain patches will become blocks in the PSDL file, make sure that they are interconnected vertex by vertex. Also make sure that each building line only stays on one border between two blocks. This is mainly an issue with the automatically generated outer ring of buildings in the city.
- Each terrain patch will become its own block, unless the flag Merge with other connected patches is set (default is true for manually placed patches, false for the ones placed automatically), in that case, when exporting, connected patches will be assigned to the same block. (connected=they share at least one edge)  
Be careful if you add railings, as they can only be placed on the block perimeter.
- Seamless intersections (two roads joined without a surface) don't become blocks. In the BAI file, roads joined this way with the same section and lanes are a single road through the blocks of all of them. Otherwise the joint becomes a two-road intersection using the block of one of the roads, where vehicles never stop. The export log shows a warning (and no BAI road is exported) for roads that end on a seamless intersection that can't be made this way (the other road is not exported, or both blocks are already used by other intersections), and for roads joined only by seamless intersections in a loop.
- If the BAI file is not present, MM2 will place the player's car in the origin point, this can cause the city to be unplayable if there is nothing there. Make sure that there is something at the origin, or alternatively shift everything in Blender (if you're using it) to make the origin contain something.
- Building meshes must be on something that will become a block, else they will not be exported to the .bin file. (as the block for the INST element cannot be determined)
- You can rename building meshes to reorder them, the order will be preserved in the INST file exported. (it can affect rendering through transparent objects)
- Road prop rules will be exported as PSDL-compatible rules if possible. (propdefs.csv and proprules.csv) This is possible for left and right rules, if the container type is PSDL-compatible. Other rules (middle, etc., and left and right if the container type is not PSDL-compatible) will have their props exported as individual props in the PATHSET file.  
Note: lines of props in the PATHSET file are not supported yet, they will be exported as individual props.

