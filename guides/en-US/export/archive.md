# Archive or loose files

## MM2 archive (.ar)

Choose **MM2 archive (.ar)** as the file type to get a single file. It is a zip archive that the game reads like its own archives. Put it in the folder of the game.

The archive contains:

- The exported files, with the same layout as a loose export
- The `geometry` and `texture` folders of the city, with your custom meshes and textures

If a custom file has the same name as an exported file, the exported file wins. Placeholder files and the `.km2-*` lists are left out.

The two preview images are written next to the archive, outside of it.

## Loose files

Choose **PSDL** as the file type to get the folders, and copy them to the game folder yourself.

## Which one to use

| | Archive | Loose files |
|---|---|---|
| Sharing or installing a city | Best: one file | Many files to copy |
| Custom textures and meshes | Included | Copy them yourself |
| Removing the city from the game | Delete one file | Find each file |
| Looking at a single file, or using the check tools | Unpack it first | Direct |
| Exporting only part of a city | Writes the archive again, with what you selected | Replaces only those files |

For most people, the archive is the simplest. Use loose files when you work on the files themselves, for example with the [check tools](checking.md).

> Don't keep an old archive and loose files of the same city in the game folder at the same time, so that you always know which version you are testing.
