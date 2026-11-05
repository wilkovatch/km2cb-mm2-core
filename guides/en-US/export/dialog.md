# The export dialog

To export, select **File → Export city**. You then:

1. Choose a folder, a name and a file type.
2. Click **Save**.
3. Set the options in the dialog that appears, and start the export.

## File types

| File type | What you get |
|---|---|
| **PSDL** | Loose files, in the same layout as the game folder |
| **MM2 archive (.ar)** | One file to put in the game folder, recommended for most cases |
| **JSON** | The city as a generic JSON file, for tools. It isn't for the game |

See [Archive or loose files](archive.md) to help you choose.

## The name

The name of the file you choose becomes the **internal name** of the city: every file is named after it, as in `city/<city>.psdl`. **Exported city file name** in the **Info** tab of the city properties sets the name suggested here. The name shown in the game comes from **City name**, in the same tab.

## What is in this guide

- [Where the files go](layout.md) shows the layout of the export.
- [The exported files](files.md) explains what each file does.
- [Export options](flags.md) explains each checkbox of the dialog.
- [Archive or loose files](archive.md) compares the two ways of exporting.
- [Checking a city](checking.md) covers validation, the log and the check tools.
