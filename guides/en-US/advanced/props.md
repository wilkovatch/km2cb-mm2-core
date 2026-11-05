# Prop types

## Where props are exported

| Source | Type | Exported as |
|---|---|---|
| Left or right rule of a road | **PSDL prop rule** | A prop rule of the game (`propdefs.csv`, `proprules.csv`) |
| Other rules of a road, such as middle | Any | Individual props in `props.pathset` |
| Left or right rule | Any other type | Individual props in `props.pathset` |
| **Prop line** | **Pathset line** | One native path in `props.pathset` |
| **Prop line** | Any other type | Individual props |
| **Polygon** | | Individual props |
| Any | **Parked cars** | The parked car file (see [Parked cars](parked-cars.md)) |

**Max number** set to 0 means 9999 for **Custom line**, **Custom** and **PSDL prop rule** entries, in the editor and in the exported files.

## Prop rules and textures

The game places prop rules only along rooms whose textures have an index below 255 in the PSDL. Otherwise it quits while loading the city, or crashes with MM2Hook.

The exporter gives the lowest indices to the textures of divided roads, and then to the rooms with props. If more than about 255 textures are still needed, it warns, and the props of those rooms aren't exported.

## Pathset line and Custom line

These look similar, but they behave differently:

| | **Pathset line** | **Custom line** |
|---|---|---|
| Model axis along the line | X | Z |
| Spacing | Stretched to fit each span | Exact |
| Short spans | A span shorter than the spacing gets no props | Follows the whole line |
| Exported as | One native path | Separate props, level |

The spacing of a **Pathset line** goes from 0.25 to 63.75 m, in quarter-meter steps. With **Project to ground** on, its props and path follow the ground. With it off, the path is the evaluated spline.

On a **Custom line**, **Rotation** turns each prop around the vertical axis. With **Project to ground**, each prop is projected separately, so the ground doesn't change where the props go along the line.

The other types have a **Width (m)** across the spline, shown by outer cyan lines.

## Polygons

A **Polygon** takes any number of models, each with a density in props per 100 square meters and a range of rotation. Its saved seed keeps the positions stable. Simple concave shapes work, but a shape that crosses itself shows an error.

## How props are drawn

The game draws a prop moved by its center of gravity, from `tune/banger/<prop>.dgBangerData`, and the editor does the same with the imported tuning files. Without them, the editor puts props with their lowest point on the ground and warns in the log, which is not always where the game draws them. Fences, for example, are drawn from one end.

A custom prop without this data sits with its lowest point on the ground.

## Limits

- `props.pathset` and the race prop files hold at most 192 paths.
- Scaling isn't supported for props.
