# AGENTS.md

Guidance for AI coding agents (and humans) working on the **Midtown Madness 2 core** of km2 City Builder. The core is installed in the builder's `Files/cores/MidtownMadness2`. Read the builder's [AGENTS.md](../../../AGENTS.md) first for the general rules (generic base builder, commits, versions, short tests, building, self-tests). [README.md](README.md) is the user-facing overview of the core; this entry file contains essential core rules and a reading index for the detailed MM2 facts and workflows.

## References

- MM2 file format specifications (needed for any change to the exporters): https://github.com/Dummiesman/angel-file-formats/tree/master/Midtown%20Madness%202. The PKG reference is https://github.com/Dummiesman/PKGImportExport.
- Machine-specific locations (the game install, the extracted stock data, the psdl-viewer) are in the builder's gitignored `CLAUDE.local.md`. Don't scan drives for them.

## Game data and documentation

Never commit original game data (`city/materials.csv`, stock `.pkg`/`.tex`/bounds, ...) to this repo. The user provides these files in the builder's gitignored `Files/common/MidtownMadness2/` folder, which mirrors the game layout (`geometry/`, `texture/`, `city/`, `jpg/`, `tune/banger/`) and is created from this core's `baseCommon/`, where only `_put ... here` placeholder files are tracked. When such a file is missing, warn and fall back to a default.

Do not put migrations information in the README, the migration process should be transparent to users.

## Releases and installs

`.github/workflows/release.yml` tags every push to `main` that changes installed files as `v<version>-<short hash>` (`version` from `settings.json`), with an annotated tag whose message is the changelog. The builder's core manager installs and updates users' copies only to these tags and shows the messages under **Show info**. Increase `version` before pushing a release that users should see as new, and keep migration-breaking work off `main` until it is complete. User installs leave out the `developerPaths` of `settings.json` (`tests`, `docs`, `AGENTS.md`, `CLAUDE.md`); add new developer-only paths there. Develop in a plain `git clone`, which keeps every file; an install from the core manager is sparse (`git sparse-checkout disable` turns it into a full checkout).

## Guides

`guides/en-US/{beginner,advanced,export}` are the guides shown in **Help > Guides** (format in the builder's `wiki/Core-Guides.md`). They are the detailed user documentation and leave out internals (the PSDL attributes, migrations). The README stays a short overview of the core (what it supports, game files, exporting, licenses) and points to the guides: don't add step-by-step instructions or feature details to it, only a line to its Features list for a major new feature. When a feature changes, update the guides: the export guide lists every flag of `exporters/psdl/settings.json` and every exported file, and the advanced guide the [limits and `mm2.log` messages](docs/agents/exporting.md#midtown-madness-2-reference). `selftest undo <new folder> --mode guide` in the builder checks their links and structure, not whether they are true.

## Coordinates

The builder and this core are left-handed, Y up, +Z forward, +X right. MM2 game files mirror X (MM2 x = -builder x, the exporters handle it). In-game north is -Z and east is +X.

## Read before working

Read every topic relevant to the task before changing the core or running its workflows. Tasks spanning several areas require all of their relevant topics. For builder code or builder-side execution/tests, also read the builder's relevant [architecture](../../../docs/agents/architecture.md), [development](../../../docs/agents/development.md) and [testing](../../../docs/agents/testing.md) notes.

| Before working on... | Read |
|---|---|
| API/undo scenarios, fixtures, focused checks or test baselines | [Developer tests](docs/agents/testing.md) and [test commands](tests/README.md) |
| Any exporter change, native engine limits, crashes or reverse-engineering setup | [Exporter workflow and engine limits](docs/agents/exporting.md) and [The PSDL exporter](docs/exporter.md) (its structure) |
| Stock asset extraction, DAVE archives, city importing or importer round trips | [Game assets and city importing](docs/agents/assets-and-importing.md) |
| PSDL rooms, BAI lanes or pedestrians, the removed PSDL attribute elements | [PSDL rooms and BAI](docs/agents/psdl-and-bai.md) |
| Prop placers/rules, banger transforms, INST modifiers, PATHSET lines or parked cars | [Props, INST and parked cars](docs/agents/props-and-parked-cars.md) |
| Decals, rail decals, texture conventions, LOD textures, HUD/menu maps or labels | [Decals, textures and maps](docs/agents/decals-textures-and-maps.md) |
| Races, opponents, difficulty, point storage, spline state or their migrations | [Races, point values and spline state](docs/agents/races-and-state.md) |
| Train/boat routes, native movement, previews, export or train migrations | [Train splines and boat paths](docs/agents/trains-and-boats.md) |
| Bridge controls, preview poses, mesh generation, tuning or race replacements | [Movable bridges](docs/agents/bridges.md) |

Paths and command examples in these topics are relative to the core root unless stated otherwise. Builder CLI and self-test commands run from the builder root.

## Maintaining these instructions

Keep essential core rules and this reading index here. Put detailed facts, commands, evidence, verification limits and migrations in their owning `docs/agents/` topic; update the index when adding a topic. Core-specific agent notes stay in this repository; generic program documentation stays in the builder wiki.

Both Codex and Claude use this index. Keep `CLAUDE.md` as `@AGENTS.md` and read linked topics on demand. Do not import every topic at startup or duplicate the guidance in Claude-specific files. Keep machine-specific local instruction files gitignored.
