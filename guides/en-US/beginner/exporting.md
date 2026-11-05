# Exporting and playing

## The simple way

1. Save the city.
2. Select **File → Validate city** and look at the list. **Errors** need fixing. Read the **warnings** too, since many mean something won't work in the game.
3. Select **File → Export city**, and choose **MM2 archive (.ar)** as the file type.
4. Choose the name of the file, and click **Save**. The name of the file becomes the internal name of the city. In the options dialog, leave the options as they are.
5. Copy the `.ar` file to the folder of the game.

The city is now in the game, in the same list as the stock cities.

The archive includes the textures and meshes in the city folder, so nothing else needs copying. The [Export guide](../export/dialog.md) explains every option, and how to export loose files instead.

## Checklist

Before you test, make sure that:

- The roads and terrain are connected, with no gaps.
- The start of each race is on a block.
- No intersection has more than 11 roads.
- No road has more than 4 lanes per side.
- Meshes and buildings stand on something that becomes a block.
- The custom textures are in the city folder.

> If you export without the BAI file, the game puts the player's car at the origin of the city, so make sure there is something there.

## If the game crashes

Look at `mm2.log` in the folder of the game, and at `mm2hook.log` if you use MM2Hook. The last lines usually show where it stopped. The [Advanced guide](../advanced/limits.md) lists the most common messages and what they mean.

The most frequent causes are too many textures, too many different meshes, or too many roads at an intersection. The exporter warns about all of these, so check its messages first.

## What's next

- The [Advanced guide](../advanced/blocks.md) covers railings, cable car details, exporting elements as meshes, low-detail textures and much more.
- The [Export guide](../export/dialog.md) explains each exported file and each export option.
