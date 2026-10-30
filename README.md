This core for km2 City Builder adds support for Midtown Madness 2 cities

The main repository for the city builder is here: https://github.com/wilkovatch/km2-city-builder

This core uses code from this repository: https://github.com/wilkovatch/psdl-exporter-common, it's included as a submodule, so make sure to use `--recurse-submodules` when cloning this repository.

## Importing the stock game assets

Open or create a city using the Midtown Madness 2 core, then choose **Scripts → Import MM2 game assets...**. Select the folder of your own MM2 installation (the folder containing `MM2CORE.AR` and `MM2TEX.AR`) and click **Run**. The script extracts the stock meshes and their MTX files, TEX and TGA textures, prop tuning (`tune/banger/*.dgBangerData`) and `city/materials.csv` to the city builder's `Files/common/MidtownMadness2` folder. The city templates already search this folder for shared assets.

Existing files are skipped by default, including names with different capitalization. Enable **Overwrite existing files** to replace matching assets with the stock versions. Unrelated files and the placeholder files are preserved. The importer reads only the two stock DAVE archives: mods, loose overrides, audio, collision bounds, city/race files and JPG images (including the optional map frame) are not imported. No extracted game data is included with the core.

The progress bar has a **Cancel** button. Completed files remain after cancellation or an error, and importing cannot be undone. Rerun with overwrite disabled to fill in the missing files. Each completed file is published only after its data has been validated; forcibly stopping the script can leave a `.km2-mm2-import-*.tmp` file, which is harmless and can be deleted. When the import finishes, it reports the destination, imported/replaced/skipped counts and bytes written. **Save and reopen the city** to refresh cached meshes, textures and prop transforms.

The SF and London city templates include building presets based on the facades of the original cities: 69 named styles for SF and 62 for London, in addition to their Default presets. They include matching building-side and building-block presets, using the original texture combinations, facade tile sizes and roof textures. Choose them in the building editor or in Whole city buildings. The stock textures must be provided in `Files/common/MidtownMadness2/texture` as usual. These are reusable procedural styles: each repeats its facade on all sides, and ground-floor slivers are adapted to editable texture blocks. The source rooms, dimensions and textures are listed in [Building presets](BUILDING_PRESETS.md). Existing cities keep their own presets; the template presets are copied when creating a new city.

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
 - CINFO and AIMAP (races, opponents, police, ambient traffic)
 - Hudmap (the map of the HUD) and race maps (the maps of the race menus)
 - BIN (select "BIN only" to save only the BIN file and use it in Blender)

The files are written as in the folder of the game, ready to be copied there (or packed in an .ar file). The PSDL goes in a `city` folder: if the chosen .psdl file is in a folder named `city`, it is used as it is, otherwise a `city` folder is created in the chosen folder. The other folders are next to the `city` folder:
```
city/<city>.psdl, .inst, .bai, .aimap
city/<city>/        props.pathset, decals.pathset, proprules.csv, propdefs.csv
tune/               <city>.cinfo, <city>.mmHudMap
race/<city>/        roam.aimap, the race aimaps, opponents and waypoints, mm*data.csv, <city>_train.pathset
geometry/           <city>_mesh<n>.pkg, hudmap_<city>.pkg
bound/              <city>_mesh<n>_BOUND.bnd/.bbnd/.ter
texture/            <city>_hudmap<n>.tex, <city>_hudmap<n>_ni.tex
jpg/                <city>_maproam.jpg, <city>_map<race>.jpg
<city>_hudmap_preview.png (a preview of the hudmap, not used by the game)
```

To get a single file instead, choose the "MM2 archive (.ar)" file type when exporting (the "Pack to .ar archive" flag is then set). The same files are written to a temporary folder and packed, with the same layout, in `<city>.ar` (a zip archive, which the game reads like its own archives), together with the `geometry` and `texture` folders of the city (the custom meshes and textures). Exported files override custom files with the same name. Only the `.ar` and `<city>_hudmap_preview.png` are written next to the chosen file. Put the `.ar` in the folder of the game.

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
  - To join visible tram rails across an intersection, use **Generate rail decals** in its panel. The button is enabled with at least two connected tram roads. It pairs the most opposite roads first, with the existing turn-angle limit, and creates editable decal elements only across the intersection. They use `r4i_rails_f`, 2 m wide; edit the generated decals to change either. Road-length decals are placed separately. Generation appends a new set each time: delete old decals manually before regenerating.
- Export to PKG
  - Check Export to PKG on a road, intersection, terrain patch or building line to export it as a mesh instead of PSDL geometry. It saves PSDL vertices and allows shapes that the PSDL can't have.
  - Roads, intersections and terrain patches still become blocks, but empty ones (with the perimeter of the element and no surface), and the element is placed in its block through the INST file. Building lines are placed in the block they are on, as usual.
  - The meshes are written to `geometry/<city>_mesh<n>.pkg` (low LOD only, used by the game at every distance) and their colliders to `bound/<city>_mesh<n>_BOUND.bnd/.bbnd/.ter`. The meshes are relative to the bottom center of their bounding box.
  - The materials of the colliders (the ground type, e.g. cobblestone or grass) come from the textures of the polygons, as in the PSDL, through the `city/materials.csv` file of the game: copy it to `Files/common/MidtownMadness2/city/materials.csv` (next to the `geometry` and `texture` folders of the game files), and add the custom textures to both copies. Without it, or for textures not in it, the colliders use the `default` material.
  - Uncheck Export PKG and bound files in the export dialog to write only the INST entries and the empty blocks (e.g. when the meshes didn't change). A collider can have at most 65535 vertices and polygons; the TER file at most 65535 polygon references (about 10 m cells), bigger ones are skipped with a warning.
- Trains
  - Choose **Create > Train** and draw a route with the usual spline point tools. Each train is an independent custom element using London's train-path behavior. The model is hardcoded by the game; train paths have no presets. Existing city-property train lines migrate automatically with a backup.
  - The always-visible yellow line previews MM2's own interpolation; a cyan control polygon appears while editing. The route is selectable while deselected and has normal surface occlusion. There is no generated train, track or tunnel mesh, and points keep their authored heights without surface projection.
  - MM2 uses cubic Hermite X/Z with fixed half-difference tangents and wrapped endpoint neighbors, but linear height between each pair of points. This train-only curve has no editable tension. The preview is static: it does not show movement or stopping positions. At least three points are needed for export; incomplete routes remain editable.
  - The authored control points are exported directly to `race/<city>/<city>_train.pathset`, as in London (type 2, spacing byte 20). Display tessellation does not change export points. Re-exporting with no valid routes removes an old train pathset at that output location.
  - The tunnels and stations are not generated: place them as mesh instances, for example with the stock London meshes (`bl_subway*`, `cl_subway*`, `kl_subway*`, `ol_subway*`, `wl_subway*`) on invisible terrain patches (empty blocks), and put the points of the line inside them (the London trains run about 13 m below the streets).

- Decals
  - The properties panel opens immediately with **Create > Decal**, so texture, width and curve mode can be chosen before placing any points. Decals support the normal preset controls and preset management, including syncing linked decals while keeping their points and attachments. The last selected or saved preset is reused for new decals during the current city session; unsaved edits are not carried over.
  - The Default preset uses the SF tram-rail texture `texture/r4i_rails_f.tex`, 2 m wide, with a Bézier spline for manual placement. Existing cities receive this Default only if their decal preset category is missing. The intersection rail generator continues to produce low-poly decals independently of the selected preset.
  - Textured strips lying on roads or the ground, like the London zigzags (`decal_zigzag_l`), yellow boxes (`decal_x_inter_l`) and San Francisco rails (`r4i_rails_f`). Choose **Create > Decal** and place its individual points as for roads. Select its texture, width and curve mode (low-poly, Bézier or Hermite); insert, remove or move points in its editor. Points project onto the surface when placed or moved. The strip remains visible when its point handles are hidden.
  - They are exported with the PATHSET, to `city/<city>/decals.pathset` (next to `props.pathset`), as the game reads it: each decal is a strip of the texture tiled along it in square tiles as wide as the strip, with a whole number of tiles in each piece. The texture must be in the game (it's not exported), its transparent parts show what's under the decal. Texture names can have at most 31 characters.
  - The game draws each piece of a decal (every segment, split every 25 m at most) only when the room (block) where it starts is visible: keep decals on the blocks, the export log warns about points outside of them.
  - `exporters/psdl/tools/decal_check.py` checks a decals.pathset file (stock or exported): the faces, the tiles and the names.

- Hudmap and race maps
  - Exported with Export hudmap and race maps (it needs the Python module Pillow, installed with the requirements of the core). The map is drawn from the geometry of the city, seen from above with the north (-z in the game) up, with the colors set in the Hudmap tab of the city properties (by default the ones of the stock San Francisco map: white roads with a grey outline, beige ground and buildings, green grass, red landmarks, blue water).
  - The hudmap is the map of the HUD in the game: tiles of 256 pixels (or 512) at 5.5 m per pixel (as the stock maps) in `texture/<city>_hudmap<n>.tex` (with a `_ni` copy for the night), placed in the city by `geometry/hudmap_<city>.pkg`, and `tune/<city>.mmHudMap` (the size and zoom of the map, as in San Francisco, and the color around it, the water color). Tiles with only water are left out. Keep the map within 16 tiles (change the meters per pixel or the tile size otherwise). `<city>_hudmap_preview.png` shows the whole map.
  - The race maps are the images of the race menus (242x184, with the frame of the menu): `jpg/<city>_maproam.jpg` (the whole city) and `jpg/<city>_map<race>.jpg` for each race (blitz0, circuit0, race0, ...: the area of its checkpoints, the start in red and the checkpoints in green). The frame is a plain color, unless a stock map image is copied to `Files/common/MidtownMadness2/jpg/mapframe.jpg`: its frame is used instead.
  - Map labels (district names, etc.) are added in the Hudmap tab of the city properties: each has a text, a size (in pixels of the race maps), an angle and a position (a point placed like the decal points). They are only drawn on the race maps, not on the hudmap.
  - Roads and intersections are drawn as roads, terrain patches as ground; both are grass or water instead by the physics material of their texture in `city/materials.csv` (grass, mud, water, deepwater) or by its name (grass, park, lawn, water, pond, river, sea); perimeter-only patches are not drawn. The roofs of the building lines are drawn as buildings, mesh instances are not drawn. Change it with the Hudmap category of roads, intersections, terrain patches, building lines, buildings and mesh instances (e.g. Landmark for the buildings in red, Ground for a walkway inside a block, or Hidden); a mesh instance is drawn as its bounding box. The parts of the roads passing through an intersection take the category of the intersection unless they have their own.
- PSDL attributes (custom elements)
  - Roads, intersections, terrain patches and building lines of type `psdl` (not exported to PKG) can be converted to the PSDL attributes they are exported to (the "Convert to PSDL attributes" button of their panel, converter `toPsdl`), to edit them one by one: each vertex of the PSDL is a control point. Converting doesn't change the export: the converter runs the exporter on the element and turns the parts it would write into the attributes.
  - The attributes are in rooms (one per room of the element), each room a block of the PSDL; the parts of a building are in a group placed in the room where the building is when exported (Scripts > Assign building parts to rooms merges them into their rooms). The roads and intersections also get their BAI road or intersection, which can be edited too (lanes, rules, connections).
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
    | `room` | A room (block) of the PSDL: contains the attributes and the BAI elements. Echo, warp, hudmap category. Its `perimeter` (a closed array, drawn as a magenta line that can be clicked to select the room) is written as it is, in the order of its points, the neighbours being the rooms sharing its points (their attributes or perimeter); with `simplifyPerimeter` the points in a straight line that lead to no other room are left out, and the spikes, as for the perimeter the exporter finds when it has none (fewer than 3 points). The button *Compute the perimeter from the contents* (converter `roomPerimeter`) sets it to the one the exporter would find, with `simplifyPerimeter`. | `perimeter` |
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

  - See the Core Custom Elements page of the wiki of the city builder for how the custom element types, their scripts and the converters are defined.

Some things to consider when creating cities:
- Changing of mesh instances scale in unsupported in MM2
- Mesh instances will be written to the INST file if not flagged as props (if flagged as props they will go in the PATHSET file)
- The game draws a prop (as the mesh instances flagged as props, the props of the prop rules and the traffic lights) with its mesh moved by its centre of gravity, the `CG` of `tune/banger/<prop>.dgBangerData`, and the editor does the same: copy the `tune/banger` folder of the game to `Files/common/MidtownMadness2/tune/banger` (next to the `geometry` and `texture` folders of the game files). The editor reads it when the city is loaded. Without it the props are put with their lowest point on the ground (a warning in the log says so), which is not always where the game draws them (e.g. the fences, drawn from one end). A prop without banger data (e.g. a custom prop) is also put with its lowest point on the ground.
- To make MM2-style buildings with no real ground floors, set the ground floor height to 0, this way only the top block will be used to make the sliver.
- Invisible terrain patches will generate empty blocks in MM2, which can contain other things. (INST buildings, PSDL buildings, etc.)
- In MM2 only horizontal scaling is supported for INST meshes visible from all angles. Furthermore, the collider will not be scaled if present.
- Road sections in MM2 must be coplanar, the MM2 template has the option to force this set. It only affects roads that bend both horizontally and vertically, but the result can be ugly for non-slight curves.
- Roads, intersections and terrain patches will become blocks in the PSDL file, make sure that they are interconnected vertex by vertex. Also make sure that each building line only stays on one border between two blocks. This is mainly an issue with the automatically generated outer ring of buildings in the city.
- `exporters/psdl/tools/psdl_check.py` checks the block perimeters of a PSDL file (stock or exported): `python psdl_check.py --verbose <file.psdl>` lists the edges inside the city that lead to no block (thin spikes and slits of a perimeter). In the game the cars that cross them leave the city ("PHYS.DeclareMover : mover not even in city" in mm2.log). The exporter removes the spikes thinner than 10 cm, e.g. at the sidewalk corners of intersections where two roads meet at a right angle. It also checks that the blocks with PSDL props only use textures with an index below 255 (see below).
- MM2 places the PSDL props (the prop rules) only along blocks whose textures have an index below 255 in the PSDL texture list, otherwise it quits while loading the city ("Invalid command"), or crashes with MM2Hook (mm2.log: exception at EIP=0045da58 after "Placing props along road segments"). The exporter gives the lowest indices to the textures of the divided roads and then to those of the blocks with props. If they still don't fit (more than about 255 textures between them), the export log shows a warning and the props of those blocks are not exported.
- MM2 can load only a limited number of different objects (the meshes of the INST file, the props and the vehicles share about 4096 slots, and each different object in the INST file takes 6 of them), past it it crashes while loading the city (mm2.log: exception at EIP=004a48d8 after "Loading objects...", followed by "memMemoryAllocator::FindHeap failed"). Instances of the same mesh count once, but each element exported to PKG (e.g. each building line with Export to PKG checked) is a different object. The export log shows a warning when the INST file has more than 597 different objects: export fewer elements to PKG, or reuse the same meshes.
- Each terrain patch will become its own block, unless the flag Merge with other connected patches is set (default is true for manually placed patches, false for the ones placed automatically), in that case, when exporting, connected patches will be assigned to the same block. (connected=they share at least one edge)  
Be careful if you add railings, as they can only be placed on the block perimeter.
- Seamless intersections (two roads joined without a surface) don't become blocks. In the BAI file, roads joined this way with the same section and lanes are a single road through the blocks of all of them. Otherwise the joint becomes a two-road intersection using the block of one of the roads, where vehicles never stop. The export log shows a warning (and no BAI road is exported) for roads that end on a seamless intersection that can't be made this way (the other road is not exported, or both blocks are already used by other intersections), and for roads joined only by seamless intersections in a loop.
- If the BAI file is not present, MM2 will place the player's car in the origin point, this can cause the city to be unplayable if there is nothing there. Make sure that there is something at the origin, or alternatively shift everything in Blender (if you're using it) to make the origin contain something.
- Building meshes must be on something that will become a block, else they will not be exported to the .bin file. (as the block for the INST element cannot be determined)
- You can rename building meshes to reorder them, the order will be preserved in the INST file exported. (it can affect rendering through transparent objects)
- Road prop rules will be exported as PSDL-compatible rules if possible. (propdefs.csv and proprules.csv) This is possible for left and right rules, if the container type is PSDL-compatible. Other rules (middle, etc., and left and right if the container type is not PSDL-compatible) will have their props exported as individual props in the PATHSET file.  
Standalone prop rules can export native PATHSET line strips when the format reproduces their evaluated placements; other rules export individual props.

Third-party software:
- The Python packages used by this core (`pythonInfo/requirements.txt`) are installed with pip from PyPI, their licenses are in `pythonInfo/licenses.txt`.
- The hudmap and race maps are drawn with Pillow, which uses the FreeType library to render the map labels. Portions of this software are copyright © The FreeType Project (https://freetype.org). All rights reserved.

## Importing an existing MM2 city

Open an MM2 city and choose **Scripts → Import MM2 city**. Select a loose `city/<name>.psdl`; the source root is detected from its folder, or can be supplied explicitly. The importer looks for BAI, INST, prop definitions/rules, prop/decal pathsets, train paths, CINFO, AIMAP and race files in that root. Extract archives separately. No original game data is included in the core.

The import appends to the open city. Rooms, attributes and AI become editable custom elements, sharing source vertices and matching existing anchors. INST objects and point props become mesh instances. Source model/texture folders are added to local asset paths, without copying assets. Missing assets use the editor's defaults and are reported. Keep the source folders available after moving the builder city.

Single-room prop rules stay attached to road custom elements. Rules spanning rooms become standalone **Prop rules**, with editable boundary ribbons and road-center distance references. Spacing and count limits continue across their segments. Native `props.pathset` line strips also stay procedural. Export writes native type-2 strips when their evaluated placement exactly matches the format's spacing/orientation semantics (1 cm position, 0.1° yaw tolerance); otherwise it writes individual props. Independent strips sharing a model remain separate.

Source city settings and traffic-model lists are applied by default; turn off **Apply source city settings** to retain the current ones. Races, decals and train lines append. Repeating the import deliberately appends again. City edits form one undo step and roll back on failure/cancellation. Asset search paths are project preferences outside undo; cancellation can leave these paths registered.

Import/re-export is a semantic conversion, not a binary-preserving round trip. BAI lane samples, permissions and connections use the existing editable types, but multi-room route membership is reduced to one owner, arbitrary BAI train splines are omitted, and distances, frames, sidewalk centers, lights and culling are regenerated. Symmetric tram rails use measured offsets. Curved pedestrian paths can differ materially. The console reports these approximations, unsupported flags/tuning, missing companions and missing assets. Source random prop choices can differ. Decals with variable widths and sheared INST transforms are approximated; maps are regenerated. Native PKG/TEX/BND/MTX and tuning assets are referenced rather than reconstructed.

Developer checks: `python scripts/importCity/_test_import_city.py` runs short synthetic parser/mapping/strip tests. `_test_builder.py` runs through the builder's script CLI with `KM2_IMPORT_TEST_FOLDER` naming a new scratch folder; it covers import, generic ribbon sampling, undo/redo, save/reload, settings, INST transforms and native strip re-export. `_roundtrip_check.py source/city/name.psdl export/city/name.psdl --sample 10 --seed 42` writes a JSON semantic audit to stdout; `--out` saves it and `--strict` fails on compared differences. `_test_stock.py` is an optional bounded check of five routes per stock city with `KM2_MM2_SOURCE_ROOT` pointing at the extracted game root. Use writable `TMP`/`TEMP` where needed. None of these tests requires committing stock assets.

`_test_sidewalks.py` uses the same builder CLI and environment variables for a short sidewalk regression: synthetic strips and end caps, plus ten fixed-seed stock attributes when a source root is supplied. It checks the generated mesh, point order, cap markers, undo/redo, save/reload and PSDL re-export.

The fixed-seed ten-route SF/London check preserves sampled lane counts and ambient permissions, with lane-position differences below 0.03 mm. Existing exporter vertex welding changes some surface vertices by up to 3.3 cm. On two curved London routes, sidewalk curves stay close but their samples at corresponding road sections shift by 10–14 m as sections are regenerated. Close lanes alone therefore do not establish equivalent pedestrian or traffic behavior. This bounded check does not replace an in-game check of a whole imported city.

### Decal migration

Core version 3 migrates manual decals from city properties into spline-driven custom elements, preserving their names, textures, widths and centerline points as low-poly splines. The normal migration creates backups first and also preserves incomplete decals for editing. The old Decals tab and automatic rail settings are removed. **Previously automatic rail decals are not baked:** generate intersection connections with the new button and place any road-length decals separately. Existing PSDL/BAI types are now grouped under **Create > PSDL element**.
