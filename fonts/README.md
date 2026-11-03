# Label font

`LiberationSans-Bold.ttf` is the unmodified Liberation Sans Bold 2.1.5 font, bundled under the SIL Open Font License 1.1 in [LICENSE](LICENSE). Upstream: [Liberation Fonts](https://github.com/liberationfonts/liberation-fonts/releases/tag/2.1.5).

SHA-256: `788abee4c806d660e8aee46689dd8540cd4bb98da03dcc9d171ce3efd99a9173`.

The exporter uses this bold sans-serif default, with letter spacing and translucent black ink, to approximate the small uppercase names baked into the stock map JPGs. Roam names use 75% of the race-map label size. The exact original face cannot be identified from the JPEGs; this is an Arial-metric-compatible substitute, not an original game font.

The core's `lua/map_label_font.lua` contains generated outline triangles and metrics from this font, under the same OFL license, with the derived name **KM2 Map Labels**. The core draws a single filled mesh at the label's preview height, without overlapping halo layers, so it has the same colour from above and below. The mesh has the same letter spacing as the exported text. Latin, Latin Extended A and common punctuation are included; other characters use the font's missing-glyph box. Export retains the complete Unicode text. An explicit city font override affects exported maps; the editor preview uses the bundled outline data.

Regenerate the outline data with `python tools/_generate_map_label_font.py` from the core folder. The development environment needs `fonttools`, `shapely`, `mapbox-earcut` and `numpy`. These are build-time tools for the font data, not runtime requirements of the core.

Stock comparisons are bounded to three visible words in SF race/roam maps and London's race map. `exporters/psdl/tools/_test_hudmap.py <builder-export.json> --stock-archive <MM2TEX.AR>` reads those originals directly from the user's archive and compares word widths and cap heights, allowing for JPEG compression. Stock images are never bundled.
