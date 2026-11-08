# Creating the city

## Choosing a template

Select **File → New city**, choose **Midtown Madness 2** in **Cores**, and pick a template:

- **San Francisco** starts from the style of the stock San Francisco.
- **London** starts from the style of the stock London.

The templates set the presets: road types, 69 named building styles for San Francisco and 62 for London, and so on. They use the stock textures you imported, so import the assets first.

A resolution and a terrain size of 4096 are a good start.

## Think about the size

The stock cities are much smaller than real ones, about 0.3 to 0.5 times the real scale. If you trace a real map, scale it down in the same way: a city at full scale has far more of everything, and soon reaches the limits of the game.

## City properties

Open **Edit → City properties**. For now, the **Info** and **AIMAP** tabs are the important ones.

In **Info**:

- **City name** is the name shown in the game menus.
- **Exported city file name** is the file name suggested when you export, and the internal name of the city in an `.ar` archive.

In **AIMAP**:

- **Left-hand traffic** makes traffic drive on the left. Set this before you start, since it also affects what you see in the editor: the lane arrows and the parked cars.
- **Speed limit** is the speed limit of the city.
- **Traffic car models** and **Pedestrian models** list what appears in the city.
- **Traffic light (1 lane)** and **Traffic light (2+ lanes)** are the models used for traffic lights.

The other tabs are covered later, in [Races](races.md) and [Maps](maps.md).

## Start small

For a first city, make something small: a few blocks of streets and a loop. You will reach the game much faster, and see what your choices look like while they are still easy to change.

The last chapter, [Exporting and playing](exporting.md), works at any stage, so try the city early and often.
