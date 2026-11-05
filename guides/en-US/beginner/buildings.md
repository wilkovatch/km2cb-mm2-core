# Buildings

MM2 cities use two kinds of building, and most cities mix them:

- **Building lines** generate facades and roofs. They are the quickest way to fill a city.
- **INST meshes** are ready-made models, good for landmarks. See [Props and meshes](props-and-meshes.md).

## Filling the city

After the terrain, select **Create → Whole city buildings**. Choose from the presets of the template, which copy the facades of the stock cities: they use the original textures, sizes and roofs.

If you want only some areas to have buildings, use invisible terrain patches for them and choose to place the buildings only on invisible patches.

## Rules for building lines

- **Keep each line on a single border between two blocks.** This is mostly a problem for the outer ring of buildings created automatically around the city.
- **Slopes are fine:** the presets fill the gaps with plain masonry, plaster or siding.

## Stock-style buildings

To make a building with no real ground floor, like most stock buildings, set the ground floor height to 0. Only the top block of the ground floor is then used, as a sliver.

## Collisions

Each facade has a collision surface in the game. If cars can sometimes drive through a building, check **Fix bound by duplicating it** in its panel, which also adds the surface to the block in front. Use it only where needed.

On a building line, it only applies when **Front only** is checked.

## Which block?

A building line is placed in the block it stands on. So a building needs something under it that becomes a block: a road, an intersection or a terrain patch, which can be invisible.
