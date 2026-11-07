# Races

Races are in **Edit → City properties**, in the tabs **Circuit races**, **Checkpoint races** and **Blitz races**. Add a race to a list and select it: while it's selected, the **Create** menu adds things to that race.

## What a race contains

Only the things of the selected race are shown, so the other races don't get in the way.

- **Checkpoints:** use **Create → Checkpoint**.
- **Props:** use the **Props** submenu of **Create**, which turns blue. These appear only in this race. Deselect the race to go back to placing ordinary props.

A blue menu in the menu bar shows the selected race, with entries to reopen or deselect it.

## Amateur and Professional

Each race has two setups, and its panel shows each setting on one row, with the amateur value on the left and the professional one on the right.

Click **Amateur** or **Professional** in the panel of the race to open that setup. With a setup open:

- **Create → Police car** adds a police car.
- **Create → Opponent** adds an opponent (not in Blitz races, which have none).

If you leave the opponents of the professional setup empty, the game uses the amateur ones.

## Opponents

The first click places the opponent's starting car. Later clicks draw the route it follows, as a line of waypoints. The panel of the opponent sets the car and how it drives.

The game doesn't look for a way between two waypoints. It follows a road only from one intersection to the next one, so:

- Put a waypoint **on every intersection** the opponent goes through, including those where it goes straight on. A waypoint in the middle of a road is ignored by the game, and the opponent goes astray.
- The last waypoint is the finish. It can be anywhere, best on the road after the last intersection.
- Between two waypoints that are not on neighboring intersections, the opponent leaves the roads and drives straight to the next one, through whatever is in the way. This is fine for a shortcut across an open square, but not through buildings.

**Check opponent routes**, in the panel of the race or of an opponent, finds these problems without exporting. It lists them, and draws over the city the way each opponent will go: green along the roads, orange where it drives straight, red where it hits a building or leaves the city. Select a problem and press **Zoom to it** to see where it is. The export lists the same problems as warnings.

## Free roaming

Police cars for free roaming are set with **Edit police cars** in the **AIMAP** tab of the city properties. While you edit them, **Create → Police car** adds to those instead.
