This core for km2 City Builder adds support for Midtown Madness 2 cities

The main repository for the city builder is here: https://github.com/wilkovatch/km2-city-builder

This core uses code from this repository: https://github.com/wilkovatch/psdl-exporter-common, it's included as a submodule, so make sure to use `--recurse-submodules` when cloning this repository.

To import the output in Blender you can use these two plugins:
- https://github.com/wilkovatch/km2cb-to-blender-mm2-plugin (to import the resulting .bin file in Blender)
- https://github.com/wilkovatch/mm2-blender-psdl-plugin (to export the PSDL and other files)

Exporters supported (accessible by selecting the PSDL format when exporting):
 - PSDL
 - BAI (still incomplete and broken)
 - INST
 - PATHSET
 - Prop rules
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
- If the BAI file is not present, MM2 will place the player's car in the origin point, this can cause the city to be unplayable if there is nothing there. Make sure that there is something at the origin, or alternatively shift everything in Blender (if you're using it) to make the origin contain something.
- Building meshes must be on something that will become a block, else they will not be exported to the .bin file. (as the block for the INST element cannot be determined)
- You can rename building meshes to reorder them, the order will be preserved in the INST file exported. (it can affect rendering through transparent objects)
- Road prop rules will be exported as PSDL-compatible rules if possible. (propdefs.csv and proprules.csv) This is possible for left and right rules, if the container type is PSDL-compatible. Other rules (middle, etc., and left and right if the container type is not PSDL-compatible) will have their props exported as individual props in the PATHSET file.  
Note: lines of props in the PATHSET file are not supported yet, they will be exported as individual props.

