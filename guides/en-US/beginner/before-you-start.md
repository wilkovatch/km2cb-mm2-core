# Before you start

This guide takes you through a complete Midtown Madness 2 city, one type of element at a time, and points out what each one needs to work in the game. It assumes you know the editor: if not, read the **Basic guide** in **Help → Guides** first.

When you want more depth, the [Advanced guide](../advanced/rooms.md) picks up where this one stops, and the [Export guide](../export/dialog.md) explains the exported files.

## Import the game assets

The core can't include the game's files, so you import them from your own copy of MM2. You need to do this only once, and any city can then use them.

1. Open or create a city with this core: the script is only available with a city open.
2. Choose **Scripts → Import MM2 game assets**.
3. Select the folder of your MM2 installation, the one containing `MM2CORE.AR` and `MM2TEX.AR`.
4. Click **Run**.
5. When it finishes, save and reopen the city, so that the editor sees the new files.

The assets go in `Files/common/MidtownMadness2`, where the city templates already look. This gives you the stock meshes and textures, the prop tuning files and `city/materials.csv`.

If you stop the import halfway, run it again: it skips the files it already has.

## Stock MM2 or MM2Hook?

The core assumes the standard game. If the city is meant to be played with MM2Hook, turn on **Assume using MM2Hook** in **Edit → City properties**, in the **Info** tab. It does three things:

- You can edit the **Roll** of road points, to bank them.
- The third parked car model appears in the examples.
- The export warnings about textures describe the limits with the hook.

The exported city is otherwise the same.

## How the game sees your city

A few facts explain most of the advice in this guide:

- **The game divides the city into rooms.** Every road, intersection and terrain patch usually becomes a room, and rooms have to connect to each other exactly, point by point.
- **Cars must always be in a room.** A car that crosses a gap between rooms leaves the city, as far as the game is concerned.
- **Roads drive the traffic.** Ambient vehicles and pedestrians follow what you set on the roads.
- **The game has limits.** Too many textures, meshes or roads at an intersection can crash it. The exporter warns you about most of them, so read its messages.
