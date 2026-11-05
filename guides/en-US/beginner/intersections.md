# Intersections

Intersections appear when you connect roads, as in the Basic guide. Each one becomes a block of the city.

Click on an intersection to set its **Sidewalk texture**, **Road texture** and **Default crosswalk texture**.

## Not too many roads

> The game crashes when ambient traffic reaches an intersection with **more than 11 roads**.

The exporter splits such an intersection into a ring of smaller ones for the traffic, and warns you. It is still better to avoid them, so don't bring too many roads to the same point.

## Traffic rules

Each end of a road has its own rule, in the **Traffic** tab of the road:

| Option | What vehicles do |
|---|---|
| **First in, first out (default)** | Take turns |
| **Traffic lights** | Wait for the lights |
| **Always stop** | Stop, then go |
| **Never stop** | Drive through |

The stock San Francisco uses **First in, first out** only at ends with 3 roads. If `mm2.log` in the game folder reports vehicles without permission to cross an intersection, try another rule there.

## Traffic lights

For the **Traffic lights** rule, the models are set in the **AIMAP** tab of the city properties, and each road can adjust its own lights in the **Traffic** tab:

- **Edit start traffic light** and **Edit end traffic light** adjust the placement of a light.
- **Place traffic lights on the opposite road** puts each light across the intersection, as in the United States.
- **Swap traffic lights sides** is for cities with left-hand traffic.

## Crosswalks

The **Inters.** tab of a road sets the crosswalk texture at each of its ends. An intersection also has a **Default crosswalk texture** for the roads that don't set one.
