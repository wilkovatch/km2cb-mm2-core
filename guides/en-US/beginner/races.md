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

- Put a waypoint **on every intersection** the opponent goes through, including those where it goes straight on. The waypoints go only on the centers of the intersections, which are shown while you add them, and they follow the intersections when you move them. A waypoint in the middle of a road would be ignored by the game.
- The last point of the route is the finish, not a waypoint. It can be anywhere, best on the road after the last intersection. To add a waypoint once the finish is placed, select the finish (in the city or in the **Waypoints** list of the panel, which shows what each point is on) and use the click mode **Add before selected**.
- Between two waypoints that are not on neighboring intersections, the opponent leaves the roads and drives straight to the next one, through whatever is in the way. This is fine for a shortcut across an open square, but not through buildings.
- In a circuit race with more than one lap, after the last waypoint before the finish the opponent goes back to the **second** waypoint, not the first: the first one is used only at the start of the first lap. If the last waypoint is not on the intersection of the first one, the opponent circles around the last waypoint until the final lap. Close the loop as the original races do:
  1. Put the start on the road leaving an intersection, and the **first waypoint on that intersection**, behind the start.
  2. Add the waypoints of the lap, around to that same intersection: the **last waypoint is on the intersection of the first one** (click the first waypoint to add it, with **Add before selected** on the finish).
  3. Put the finish after it, on the road of the start.

  For example, with the start on the road from intersection A to B, a lap A, B, C, D, A is the route **A, B, C, D, A, finish**.

**Check opponent routes**, in the panel of the race or of an opponent, finds these problems without exporting. It lists them, and draws over the city the way each opponent will go: green along the roads, orange where it drives straight, red where it hits a building or leaves the city. Select a problem and press **Zoom to it** to see where it is. The export lists the same problems as warnings.

## Free roaming

Police cars for free roaming are set with **Edit police cars** in the **AIMAP** tab of the city properties. While you edit them, **Create → Police car** adds to those instead.

## Cops & Robbers

In the multiplayer Cops & Robbers mode, each round places the gold, the bank and the hideout. Choose where they can go with **Edit Cops & Robbers spots** in the **Cops & Robbers** tab of the city properties. While you edit them, **Create → Cops & Robbers spot** adds a spot where you click.

The game places each of the three on one of your spots half of the time, and on a random road the other half, as in the stock cities. Without spots, they always go on random roads. Put the spots on roads or other places a car can reach, inside the city: the export warns about a spot that is not over any part of the city.

The spots are shown with the gold model, `wpobj_gold.pkg`, when it's in the `geometry` folder of your game files.
