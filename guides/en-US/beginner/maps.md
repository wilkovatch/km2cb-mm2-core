# Maps

The exporter draws the maps of your city by itself, in two forms:

- The **hudmap** is the map on the screen while driving.
- The **race maps** are the small images in the race menus.

So you don't have to do anything for a working map, but you can improve it.

## Hudmap settings

Open the **Hudmap** tab of **Edit → City properties**:

- **Meters per pixel** and **Tile size** set the detail. The stock maps use 5.5 and 256. **Keep the map within 16 tiles:** on a big city, use more meters per pixel or the bigger tile size.
- The colors are set here too. The defaults are those of the stock San Francisco.

## What appears on the map

Roads, intersections and movable bridges are drawn as roads, terrain patches as ground, and the roofs of building lines as buildings. Grass and water are detected from the texture. Small blue arrows show the direction of the one-way roads, as in the stock cities. To leave them out, check **Hide arrows** in the **Hudmap** tab.

To change how something appears, use **Hudmap category** in its panel. For example, set a building to **Landmark** to draw it in red. Mesh instances are not drawn, unless you give them a category.

## Map labels

For district names and parks, use **Create → Map label** while the **Hudmap** tab is open. Each label has a text, a size, an angle and a position.

Labels appear only on the images of the menus, not on the map while driving. In the editor they float 5 m above the ground in white, to make them easier to place: this isn't what they look like on the map.

## Checking the result

The export also writes two images next to the city, `<city>_hudmap_preview.png` and `<city>_hudmap_labels_preview.png`, so you can see the map without starting the game.
