# Decals

Decals are textures that lie on the roads and the ground, such as rails, zigzag lines and yellow boxes. They are in **Create → Decals**:

- **Spline** is a strip that follows points you place, like a road. Choose its texture, width and curve mode.
- **Single** is one textured rectangle. You place it with one click and edit it like a mesh: W moves, E rotates, R scales.

Their height follows the surface below them, so you only need to place them where you want them.

## Rules for the game

- **Keep decals on the rooms.** The game draws each piece of a decal only when the room where it starts is visible. The export log warns about points outside of rooms.
- **The texture has to be in the game.** A decal's texture isn't exported with it, except in the archive, which includes the textures of the city folder. Transparent areas of the texture show what's under the decal.
- **Keep texture names to 31 characters.**
- **Keep a single decal under 25 m.**

A texture is tiled along the decal in square tiles, as wide as the decal itself.

## Useful stock textures

| Texture | What it is |
|---|---|
| `r4i_rails_f` | San Francisco tram rails |
| `decal_zigzag_l` | London zigzag lines |
| `decal_x_inter_l` | London yellow boxes |

The preset named **Default** uses the rails, 2 m wide.
