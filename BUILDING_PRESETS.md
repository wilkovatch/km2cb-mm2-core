# Building presets from the original cities

Each row identifies the original PSDL room (decimal) used for the reusable facade style. The source coordinates and assets are not distributed. Buildings repeat the selected facade on all four sides; these are procedural adaptations, not copies of landmark geometry. Ground slivers become editable ground-floor texture blocks, with sliver blocks for slope infill. Upper facade bands retain their measured tile sizes; the largest band repeats when the height changes, while lower bands and roof trim stay at the bottom/top. Depth comes from the adjoining roof footprint.

Slope infill (the ground floor bottom and top blocks) uses plain wall surfaces, selected separately from the middle ground-floor texture. Stock companion masonry, plaster and siding are used where suitable; other styles use the closest stock wall surface by material and colour. Dedicated window slivers remain in the middle ground-floor blocks where the original facade used them. The Sliver column records the chosen slope-infill texture for every style. Victorian siding can also serve as its own sliver because it is already a plain wall.

The Default building and side use the first named style in each template. The standalone sliver block presets list the same wall surfaces used by the sides. Existing cities retain their saved presets; these changes apply to new cities made from the templates.

## SF

69 named buildings/sides plus Default; 116 named blocks plus Default.

| Preset | Room | Height (m) | Depth (m) | Ground texture | Upper textures | Roof | Sliver |
|---|---:|---:|---:|---|---|---|---|
| City apartments - 3S 06 | 133 | 21.375 | 11.886 | mf_soma_shop01_door_4_f | sf_3s_win06_6_f | nl_coitrock_f | sf_gsliver04_4_f |
| City apartments - 1S 04 | 63 | 13.422 | 4.494 | sf_storewin04_4_f | sf_1s_win04_4_f | nl_coitrock_f | gf_bung_brick_mat_4_f |
| City apartments - 1S 02 | 57 | 12.903 | 13.279 | sf_storewin04_4_f | sf_1s_win02_4_f | nl_coitrock_f | sf_gsliver01_4_f |
| City apartments - 2S 01 | 70 | 10.642 | 4.647 | sf_storewin04_4_f | sf_2s_win01_5_f | nl_coitrock_f | sf_gsliver08_4_f |
| City apartments - 2S 03 | 88 | 13.495 | 36.933 | mf_soma_shop05_door_4_f | sf_2s_win03_5_f | nl_coitrock_f | sf_gsliver08_4_f |
| City apartments - 2S 04 | 103 | 10.064 | 41.33 | sf_storedoor01_4_f | sf_2s_win04_5_f | nl_coitrock_f | sf_gsliver01_4_f |
| City apartments - 2S 07 | 150 | 16.173 | 19.594 | mf_soma_shop05_door_4_f | sf_2s_win07_5_f | nl_coitrock_f | sf_gsliver03_4_f |
| City apartments - 2S 10 | 148 | 17.13 | 24.78 | sf_storewin01_4_f | sf_2s_win10_5_f | nl_coitrock_f | sf_gsliver07_4_f |
| City apartments - 2S 11 | 148 | 17.423 | 20.748 | nf_coit_shop01_door_4_f | sf_2s_win11_5_f | nl_coitrock_f | sf_gsliver08_4_f |
| City apartments - 2S 13 | 166 | 17.25 | 17.027 | sf_storewin01_4_f | sf_2s_win13_5_f | nl_coitrock_f | sf_gsliver03_4_f |
| City apartments - 2S 18 | 134 | 17.645 | 27.074 | sf_storedoor02_4_f | sf_2s_win18_5_f | nl_coitrock_f | sf_gsliver08_4_f |
| City apartments - 3S 05 | 133 | 17.54 | 28.963 | mf_soma_shop01_door_4_f | sf_3s_win05_6_f | nl_coitrock_f | sf_gsliver04_4_f |
| City apartments - 3S 07 | 23 | 18.517 | 15.967 | sf_winsliver06_4_f | sf_3s_win07_6_f | nl_coitrock_f | sf_gsliver08_4_f |
| City apartments - 3S 08 | 111 | 20.938 | 21.391 | ef_office07_door_6_f | sf_3s_win08_6_f | nl_coitrock_f | sf_gsliver05_4_f |
| City apartments - 4S 01 | 24 | 20.495 | 36.108 | nf_coitbiz_office01_frt_door_f | sf_4s_win01_8_f | nl_coitrock_f | sf_gsliver03_4_f |
| City apartments - 4S 03 | 42 | 16.978 | 11.102 | nf_coitbiz_office01_frt_door_f | sf_4s_win03_8_f | nl_coitrock_f | sf_gsliver07_4_f |
| Bungalow - Blue | 149 | 15.37 | 21.665 | gf_bung_offwhite_win_4_f | gf_bung_blue_win_4_f | nl_coitrock_f | gf_bung_blue_mat_4_f |
| Bungalow - Brick | 33 | 17.406 | 27.819 | gf_bung_brick_win_4_f | gf_bung_brick_win_4_f | nl_coitrock_f | gf_bung_brick_mat_4_f |
| Bungalow - Off-white | 200 | 14.781 | 17.092 | gf_bung_tan01_win_4_f | gf_bung_offwhite_win_4_f | nl_coitrock_f | gf_bung_offwhite_mat_4_f |
| Bungalow - Peach | 20 | 16.436 | 27.584 | gf_bung_peach01_win_4_f | gf_bung_peach01_win_4_f | nl_coitrock_f | gf_bung_peach01_mat_4_f |
| Bungalow - Tan | 5 | 13.504 | 23.495 | nf_columbus_shop03_door_4_f | gf_bung_tan01_win_4_f | nl_coitrock_f | gf_bung_tan01_mat_4_f |
| Victorian - Off-white wood | 204 | 13.168 | 39.946 | gf_ggvict_offwhite_wood_4_f | gf_ggvict_offwhite_wood_4_f | sw_roof_tar01_s | gf_ggvict_offwhite_wood_4_f |
| Victorian - Blue wood | 200 | 9.999 | 17.871 | gf_ggvict_blue_wood_4_f | gf_ggvict_blue_wood_4_f | sw_roof_tar01_s | gf_ggvict_blue_wood_4_f |
| Victorian - Gray wood | 198 | 10.091 | 29.979 | gf_ggvict_gray_wood_4_f | gf_ggvict_gray_wood_4_f | sw_roof_tar01_s | gf_ggvict_gray_wood_4_f |
| Victorian - Green wood | 198 | 10.002 | 29.979 | gf_ggvict_green_wood_4_f | gf_ggvict_green_wood_4_f | sw_roof_tar01_s | gf_ggvict_green_wood_4_f |
| Victorian - Yellow wood | 198 | 10.003 | 29.98 | gf_ggvict_yellow_wood_4_f | gf_ggvict_yellow_wood_4_f | sw_roof_tar01_s | gf_ggvict_yellow_wood_4_f |
| Victorian - Brown shingles | 203 | 10.997 | 31.984 | gf_ggvict_offwhite_wood_4_f | gf_ggvict_shglbrown_wood_4_f | sw_roof_tar01_s | gf_ggvict_shglbrown_wood_4_f |
| Stucco apartments - Cream | 32 | 17.005 | 23.102 | sw_stc_cream_nonbay_f | sw_stc_cream_nonbay_f | nl_coitrock_f | gf_bung_offwhite_mat_4_f |
| Stucco apartments - Gray | 200 | 14.578 | 23.974 | sw_stc_gray_nonbay_f | sw_stc_gray_nonbay_f | nl_coitrock_f | sf_gsliver07_4_f |
| Stucco apartments - Green | 198 | 15.315 | 23.993 | sw_stc_green_nonbay_f | sw_stc_green_nonbay_f | nl_coitrock_f | sf_gsliver05_4_f |
| Stucco apartments - Off-white | 77 | 14.65 | 10.3 | gf_bung_blue_win_4_f | sw_stc_offwhite_nonbay_f | s_concrt | gf_bung_offwhite_mat_4_f |
| Stucco apartments - Peach | 160 | 15.659 | 26.938 | sw_stc_peach_nonbay_f | sw_stc_peach_nonbay_f | nl_coitrock_f | gf_bung_peach01_mat_4_f |
| Stucco apartments - Tan | 42 | 14.165 | 19.051 | sw_stc_tan_nonbay_f | sw_stc_tan_nonbay_f | nl_coitrock_f | sf_gsliver03_4_f |
| Stucco apartments - Yellow | 42 | 13.663 | 11.678 | sw_stc_yellow_bdoor_f | sw_stc_yellow_nonbay_f | nl_coitrock_f | gf_bung_tan01_mat_4_f |
| Brick apartments - Red | 21 | 13.559 | 28.121 | sw_stc_redbrick_bdoor_f | sw_stc_redbrick_nonbay_f | nl_coitrock_f | sf_gsliver01_4_f |
| Brick apartments - Brown | 68 | 15.269 | 24.053 | sw_stc_brownbrick_nonbay_f | sw_stc_brownbrick_nonbay_f | nl_coitrock_f | sf_gsliver01_4_f |
| Coit apartments 01 | 69 | 14.0 | 15.437 | nf_columbus_shop03_door_4_f | nf_coit_aptment01_win_4_f | nl_coitrock_f | gf_bung_tan01_mat_4_f |
| Coit apartments 02 | 114 | 13.219 | 21.696 | nf_coit_aptment02_win_4_f | nf_coit_aptment02_win_4_f | nl_coitrock_f | sf_gsliver03_4_f |
| Coit apartments 03 | 47 | 16.76 | 30.35 | sf_storedoor02_4_f | nf_coit_aptment03_win_4_f | nl_coitrock_f | gf_ggvict_gray_wood_4_f |
| Coit apartments 04 | 207 | 16.348 | 11.791 | gf_bung_tan01_win_4_f | nf_coit_aptment04_win_4_f | nl_coitrock_f | gf_ggvict_shglbrown_wood_4_f |
| Nob Hill apartments 01 | 142 | 22.25 | 26.602 | cf_nobhill_apt02_sliverwin_6_f | cf_nobhill_apt01_win_6_f | nl_coitrock_f | gf_bung_offwhite_mat_4_f |
| Nob Hill apartments 02 | 25 | 21.081 | 35.028 | cf_nobhill_apt01_door_6_f | cf_nobhill_apt02_win_6_f | nl_coitrock_f | gf_bung_offwhite_mat_4_f |
| Nob Hill mansion | 98 | 6.047 | 7.958 | sf_gsliver08_4_f | cf_nobhill_mansion_win_4_f | nl_coitrock_f | sf_gsliver08_4_f |
| SoMa shop 02 | 41 | 13.003 | 19.987 | gf_bung_brick_win_4_f | mf_soma_shop02_win_4_f | sw_roof_tar01_s | sf_gsliver08_4_f |
| SoMa shop 04 | 90 | 11.216 | 14.581 | mf_soma_shop05_door_4_f | mf_soma_shop04_win_4_f | nl_coitrock_f | sf_gsliver07_4_f |
| SoMa shop 05 | 93 | 10.854 | 40.024 | mf_soma_shop05_door_4_f | mf_soma_shop05_win_4_f | nl_coitrock_f | sf_gsliver08_4_f |
| SoMa shop 06 | 85 | 10.345 | 16.935 | mf_soma_warehouse07_door_6_f | mf_soma_shop06_win_4_f | nl_coitrock_f | sf_gsliver03_4_f |
| SoMa shop 07 | 90 | 11.253 | 28.618 | mf_soma_warehouse01_wall_6_f | mf_soma_shop07_win_6_f | nl_coitrock_f | sf_gsliver03_4_f |
| SoMa shop 08 | 64 | 15.874 | 27.055 | nf_coit_shop01_door_4_f | mf_soma_shop08_win_6_f | nl_coitrock_f | sf_gsliver08_4_f |
| SoMa shop 09 | 20 | 13.34 | 15.985 | mf_soma_shop09_door_4_f | mf_soma_shop09_win_4_f | nl_coitrock_f | sf_gsliver04_4_f |
| SoMa warehouse 01 | 88 | 16.006 | 35.014 | mf_soma_warehouse08_wall_6_f | mf_soma_warehouse01_wall_6_f | nl_coitrock_f | sf_gsliver03_4_f |
| SoMa warehouse 08 | 93 | 13.74 | 17.491 | mf_soma_warehouse06_door_8_f | mf_soma_warehouse08_wall_6_f | nl_coitrock_f | sf_gsliver07_4_f |
| Columbus shop 01 | 42 | 15.165 | 29.073 | nf_columbus_shop01_door_4_f | nf_columbus_shop01_win_4_f | nl_coitrock_f | sf_gsliver04_4_f |
| Columbus shop 02 | 53 | 19.307 | 14.838 | nf_columbus_shop02_door_4_f | nf_columbus_shop02_win_4_f | sw_roof_tar01_s | sf_concrete_5 |
| Cannery brick building | 86 | 17.375 | 30.959 | mf_soma_warehouse02_door_4_f | nf_cannery_brickwin_8_f | nl_coitrock_f | sf_gsliver04_4_f |
| Pier 39 wooden shop | 262 | 11.0 | 31.04 | nf_pier39shop_f | nf_pier39woodwin02_f | sw_roof_tar01_s | gf_ggvict_gray_wood_4_f |
| Coit office 02 | 82 | 11.842 | 20.285 | nf_coitbiz_office02_door_f | nf_coitbiz_office02_win_f | nl_coitrock_f | sf_concrete_5 |
| Motel | 24 | 17.098 | 11.916 | nf_coitbiz_office02_win_f | sf_2s_motel01_5_f | nl_coitrock_f | sf_gsliver08_4_f |
| Union Square hotel | 12 | 27.506 | 8.548 | ef_union_hotel01_doorside_8_f | ef_union_hotel01_win_8_f | nl_coitrock_f | sf_gsliver07_4_f |
| City office - 2S 03 | 81 | 18.998 | 11.154 | mf_soma_shop05_door_4_f | sf_2s_officewin03_5_f | nl_coitrock_f | sf_gsliver07_4_f |
| City office - 3S 01 | 145 | 70.578 | 61.227 | ef_office06_door_6_f | sf_3s_officewin01_8_f | nl_coitrock_f | sf_gsliver08_4_f |
| City office - 4S 01 | 61 | 35.194 | 19.413 | ef_office02_door_8_f | sf_4s_officewin01_8_f | nl_coitrock_f | sf_gsliver03_4_f |
| City office - 4S 02 | 81 | 42.5 | 43.343 | ef_office02_door_8_f | sf_4s_officewin02_8_f | nl_coitrock_f | sf_gsliver03_4_f |
| City office - 4S 03 | 23 | 22.495 | 31.236 | mf_soma_shop05_door_4_f | sf_4s_officewin03_8_f | nl_coitrock_f | sf_gsliver08_4_f |
| City office - 4S 04 | 6 | 26.743 | 40.859 | mf_soma_shop05_win_4_f | sf_4s_officewin04_8_f | nl_coitrock_f | sf_gsliver08_4_f |
| City office - 4S 07 | 23 | 23.864 | 27.372 | mf_soma_shop05_door_4_f | sf_4s_officewin07_8_f | nl_coitrock_f | sf_gsliver07_4_f |
| Marble office 01 | 26 | 33.504 | 11.037 | cf_marble03_door_6_f | cf_marble01_win_5_f | nl_coitrock_f | sf_gsliver08_4_f |
| Marble office 02 | 27 | 21.735 | 24.551 | ef_office01_door_6_f | cf_marble02_win_5_f | nl_coitrock_f | sf_gsliver08_4_f |
| Marble columned office | 13 | 16.23 | 10.972 | cf_marble02_win_5_f | cf_marblecolumns02_win_6_f | nl_coitrock_f | gf_bung_offwhite_mat_4_f |

## London

62 named buildings/sides plus Default; 124 named blocks plus Default.

| Preset | Room | Height (m) | Depth (m) | Ground texture | Upper textures | Roof | Sliver |
|---|---:|---:|---:|---|---|---|---|
| Red brick 04 | 141 | 28.0 | 7.961 | sf_base_white07b_1s_5_l | sf_win_brickred04_2s_4_l | sw_roof_tar01_s | sf_gsliver01_4_f |
| Red brick 01 | 103 | 20.0 | 25.015 | sf_base_tan13_1s_5_l | sf_win_office10_2s_5_l, sf_win_brickred01_1s_4_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | sf_gsliver04_4_f |
| Red brick 02 | 129 | 24.0 | 16.053 | sf_base_tan01a_1s_4_l | sf_base_tan11_1s_5_l, sf_win_office10_2s_5_l, sf_win_brickred02_2s_4_l | sw_roof_tar01_s | sf_gsliver04_4_f |
| Red brick 03 | 128 | 22.032 | 37.375 | sf_base_brickred06_1s_5_l | sf_win_brickred03_2s_4_l, sf_roof09_1s_4_l | sw_roof_tar01_s | gf_bung_brick_mat_4_f |
| Red brick 05 | 52 | 21.0 | 34.82 | sf_base_tan01a_1s_4_l | sf_win_brickred01_1s_4_l, sf_win_brickred05_2s_4_l, sw_stc_cream_pediment_f | sw_roof_tar01_s | sf_gsliver04_4_f |
| Red brick 06 | 175 | 15.66 | 11.767 | sf_base_white08a_1s_5_l | sf_win_brickred06_1s_4_l | sw_roof_tar01_s | sf_gsliver01_4_f |
| Red brick 08 | 140 | 22.0 | 11.245 | sf_base_white01a_1s_5_l | sf_win_brickred09_2s_6_l, sf_win_brickred08_2s_6_l, sf_roof07_1s_4_l | sw_roof_tar01_s | sf_gsliver06_4_f |
| Red brick 09 | 14 | 23.0 | 35.908 | ef_office05_door_6_f | sf_win_brickred09_2s_6_l, sf_win_brickred08_2s_6_l, sf_roof09_1s_4_l | sw_roof_tar01_s | sf_gsliver06_4_f |
| Red brick 10 | 14 | 20.0 | 17.925 | sf_base_brickred06_1s_5_l | sf_win_brickred11_1s_4_l, sf_win_brickred10_1s_4_l, sw_stc_cream_pediment_f | sw_roof_tar01_s | sf_gsliver01_4_f |
| Red brick 11 | 14 | 20.0 | 11.975 | sf_base_tan13_1s_5_l | sf_win_brickred11_1s_4_l, sf_roof01_1s_4_l | sw_roof_tar01_s | sf_gsliver01_4_f |
| Red brick 14 | 25 | 21.0 | 40.374 | sf_base_brickred06_1s_5_l | sf_win_brickred14_2s_6_l, sf_win_brickred03_2s_4_l, sf_roof01_1s_4_l | sw_roof_tar01_s | gf_bung_brick_mat_4_f |
| Red brick 15 | 128 | 23.027 | 12.097 | sf_base_white06b_1s_5_l | sf_win_brickred15_2s_6_l, sf_roof07_1s_4_l | sw_roof_tar01_s | sf_gsliver01_4_f |
| Red brick 16 | 38 | 23.0 | 30.382 | sf_store13a_1s_5_l | sf_win_brickred13_2s_6_l, sf_win_brickred16_2s_6_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | sf_gsliver01_4_f |
| Red brick 17 | 12 | 18.189 | 13.871 | kf_shop04a_1s_4_l | sf_win_brickred17_1s_4_l | sw_roof_tar01_s | gf_bung_offwhite_mat_4_f |
| Red brick 18 | 152 | 17.001 | 13.807 | sf_store10_2s_5_l | sf_win_brickred18_1s_4_l | sw_roof_tar01_s | sf_gsliver01_4_f |
| Red brick 19 | 37 | 17.0 | 22.752 | sf_base_brickred06_1s_5_l | sf_win_brickred19_1s_4_l, sf_win_brickred21_1s_4_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | sf_gsliver01_4_f |
| Red brick 20 | 11 | 27.0 | 52.185 | ef_office06_door_6_f | sf_win_white02_2s_6_l, sf_win_brickred20_1s_4_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | sf_gsliver01_4_f |
| Red brick 21 | 35 | 20.0 | 18.13 | sf_store12b_1s_4_l | sf_win_brickred19_1s_4_l, sf_win_brickred21_1s_4_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | sf_gsliver04_4_f |
| Brown brick 01 | 141 | 29.0 | 26.217 | sf_base_white07b_1s_5_l | sf_win_white07_2s_5_l, sf_win_brickbrn01_2s_5_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | sf_gsliver01_4_f |
| Brown brick 02 | 9 | 20.0 | 20.73 | sf_base_white04_1s_5_l | sf_win_brickbrn02b_1s_4_l, sf_win_white01_2s_4_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | sf_gsliver01_4_f |
| Cherry brick 01 | 229 | 20.0 | 16.456 | sf_store01b_2s_5_l | sf_win_brickcherry01a_1s_4_l | sw_roof_tar01_s | sf_gsliver04_4_f |
| Cherry brick 02 | 103 | 20.0 | 21.373 | kf_har_base02_1s_5_l | sf_win_brickcherry01b_1s_4_l | sw_roof_tar01_s | sf_gsliver04_4_f |
| Yellow brick 01 | 104 | 24.0 | 14.362 | kf_shop03b_1s_4_l | sf_base_tan17_2s_6_l, sf_win_brickyel01_2s_4_l, sw_stc_cream_pediment_f | sw_roof_tar01_s | sf_wall_brickyel01_l |
| Yellow brick 02 | 176 | 18.242 | 42.212 | sf_base_white01a_1s_5_l | sf_win_brickyel02_2s_5_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | sf_wall_brickyel01_l |
| Beige apartments 03 | 12 | 19.198 | 18.324 | sf_base_white06a_1s_5_l | sf_win_beige03_2s_4_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | gf_bung_offwhite_mat_4_f |
| Beige apartments 04 | 36 | 17.0 | 18.64 | sf_store18b_1s_6_l | sf_win_beige04_1s_4_l, sf_win_brickred04_2s_4_l, sw_stc_cream_pediment_f | sw_roof_tar01_s | sf_gsliver03_4_f |
| Beige apartments 05 | 37 | 17.0 | 24.872 | sf_store12b_1s_4_l | sf_win_beige05_2s_4_l, sf_win_beige09_1s_4_l, sf_top_white01_t1_1_l | s_grass | sf_gsliver03_4_f |
| Beige apartments 07 | 11 | 22.0 | 52.123 | sf_store17b_1s_6_l | sf_win_beige07_1s_4_l | sw_roof_tar01_s | sf_gsliver06_4_f |
| Beige apartments 09 | 100 | 23.0 | 20.227 | kf_har_base01_1s_5_l | sf_win_beige09_1s_4_l | sw_roof_tar01_s | sf_gsliver03_4_f |
| Beige apartments 11 | 140 | 16.0 | 21.259 | sf_store13b_1s_5_l | sf_win_beige11_2s_6_l | sw_roof_tar01_s | gf_bung_offwhite_mat_4_f |
| Beige apartments 12 | 3 | 24.0 | 19.257 | cf_marble02_win_5_f | sf_win_beige12_2s_6_l, sf_win_office07_2s_5_l, sw_stc_cream_pediment_f | sw_roof_tar01_s | gf_bung_offwhite_mat_4_f |
| White apartments 01 | 91 | 20.15 | 31.887 | sf_base_tan05_2s_4_l | sf_win_white01_2s_4_l, sf_top_white01_t1_1_l, sf_roof09_1s_4_l | sw_roof_tar01_s | gf_bung_offwhite_mat_4_f |
| White apartments 02 | 240 | 20.004 | 17.705 | sf_store04b_2s_5_l | sf_win_white02_2s_6_l, sf_win_white09_1s_5_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | gf_bung_offwhite_mat_4_f |
| White apartments 07 | 12 | 18.52 | 7.237 | sf_base_tan07b_1s_4_l | sf_win_white07_2s_5_l, sw_stc_cream_pediment_f | sw_roof_tar01_s | gf_bung_offwhite_mat_4_f |
| White apartments 08 | 22 | 20.0 | 20.405 | sf_base_tan13_1s_5_l | sf_win_white08_1s_4_l | s_concrt | gf_bung_offwhite_mat_4_f |
| White apartments 09 | 132 | 29.0 | 23.239 | sf_base_white06a_1s_5_l | sf_win_white09_1s_5_l, sf_top_white01_t1_1_l, sf_roof07_1s_4_l | sw_roof_tar01_s | gf_bung_offwhite_mat_4_f |
| Brown apartments | 214 | 20.001 | 14.048 | cf_marble02_win_5_f | sf_base_tan04_1s_4_l, sf_win_brown01_1s_4_l, sw_stc_cream_pediment_f | sw_roof_tar01_s | sf_gsliver06_4_f |
| Green apartments | 38 | 20.0 | 61.724 | sf_store18a_1s_6_l | sf_win_green03_2s_4_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | sf_gsliver05_4_f |
| Light blue apartments 04 | 175 | 16.399 | 10.967 | sf_base_white06b_1s_5_l | sf_win_ltblue05_2s_5_l, sf_win_ltblue04_2s_5_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | gf_bung_blue_mat_4_f |
| Light blue apartments 05 | 13 | 16.324 | 18.516 | sf_store18a_1s_6_l | sf_win_ltblue05_2s_5_l, sf_win_ltblue04_2s_5_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | gf_bung_blue_mat_4_f |
| Pink apartments | 13 | 14.256 | 11.454 | kf_shop09_1s_4_l | sf_win_pink03_2s_4_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | gf_bung_peach01_mat_4_f |
| Yellow apartments | 13 | 19.123 | 27.584 | sf_base_white06a_1s_5_l | sf_win_yellow03_2s_4_l, sf_top_white01_t1_1_l | sw_roof_tar01_s | gf_bung_tan01_mat_4_f |
| Office 01 | 105 | 16.0 | 23.462 | ef_shop10_win_6_f | sf_win_office01_1s_4_l | sw_roof_tar01_s | sf_gsliver07_4_f |
| Office 02 | 117 | 25.0 | 13.691 | sf_storewin02_4_f | sf_win_office02_2s_4_l | sw_roof_tar01_s | sf_gsliver07_4_f |
| Office 04 | 20 | 18.0 | 19.252 | sf_base_brickred07_1s_5_l | sf_win_brickred18_1s_4_l, sf_win_office04_2s_6_l, sw_stc_cream_pediment_f | sw_roof_tar01_s | sf_gsliver03_4_f |
| Office 06 | 138 | 18.0 | 11.883 | sf_store17b_1s_6_l | sf_win_office06_1s_4_l | sw_roof_tar01_s | sf_gsliver03_4_f |
| Office 07 | 210 | 20.0 | 17.66 | ef_shop01_win_6_f | sf_win_beige12_2s_6_l, sf_win_office07_2s_5_l, sw_stc_cream_pediment_f | sw_roof_tar01_s | sf_gsliver03_4_f |
| Office 08 | 47 | 20.0 | 22.615 | ef_office04_win_6_f | sf_win_office08_3s_6_l | sw_roof_tar01_s | sf_gsliver03_4_f |
| Office 10 | 135 | 28.0 | 37.199 | ef_office05_door_6_f | sf_base_tan13_1s_5_l, sf_win_office10_2s_5_l, sf_base_tan11_1s_5_l | sw_roof_tar01_s | sf_gsliver07_4_f |
| City commercial 01 | 76 | 25.0 | 21.371 | ef_office01_door_6_f | sf_win_office10_2s_5_l, wf_win_city01_2s_6_l, sw_stc_cream_pediment_f | sw_roof_tar01_s | gf_bung_offwhite_mat_4_f |
| City commercial 02 | 35 | 17.0 | 24.87 | sf_store08b_1s_4_l | wf_win_city02_2s_6_l, sw_stc_cream_pediment_f | sw_roof_tar01_s | sf_gsliver03_4_f |
| Kensington beige apartments 01 | 138 | 12.0 | 19.935 | kf_shop01b_1s_4_l | kf_win_beige01_2s_4_l | sw_roof_tar01_s | sf_gsliver05_4_f |
| Kensington beige apartments 02 | 13 | 13.366 | 10.245 | kf_shop03b_1s_4_l | kf_win_beige02_2s_4_l | sw_roof_tar01_s | gf_bung_offwhite_mat_4_f |
| Kensington Harrods-style facade | 38 | 23.0 | 45.358 | ef_office05_door_6_f | sf_base_tan13_1s_5_l, kf_har_top_1s_4_l, kf_har_win03_1s_4_l | sw_roof_tar01_s | sf_gsliver03_4_f |
| Waterfront warehouse | 231 | 23.0 | 13.668 | ef_office05_door_6_f | bl_waterwintop_l, sw_stc_cream_pediment_f | sw_roof_tar01_s | sf_gsliver07_4_f |
| Office base 07 | 211 | 29.0 | 17.029 | ef_office06_win_6_f | sf_base_tan14_1s_5_l, sf_base_office07_2s_6_l, sf_base_office09_1s_4_l | sw_roof_tar01_s | sf_gsliver03_4_f |
| Office base 09 | 7 | 25.0 | 42.436 | ef_office07_door_6_f | sf_base_tan14_1s_5_l, sf_base_office07_2s_6_l, sf_base_office09_1s_4_l | sw_roof_tar01_s | sf_gsliver03_4_f |
| White commercial building | 129 | 26.0 | 27.944 | sf_base_white06a_1s_5_l | sf_base_white03_win_2s_6_l, sf_top_white01_t1_1_l, sf_roof07_1s_4_l | sw_roof_tar01_s | gf_bung_offwhite_mat_4_f |
| Marble office | 38 | 23.0 | 35.738 | cf_marble03_door_6_f | cf_marblecolumns02_win_6_f, cf_marble02_win_5_f, sf_top_white01_t1_1_l | sw_roof_tar01_s | gf_bung_offwhite_mat_4_f |
| Marble columned office | 72 | 26.0 | 49.516 | cf_marble03_door_6_f | cf_marblecolumns02_win_6_f, cf_marble02_win_5_f, sf_top_white01_t1_1_l | sw_roof_tar01_s | gf_bung_offwhite_mat_4_f |
| Commercial office - 3S | 49 | 22.0 | 26.286 | sf_storewin02_4_f | sf_3s_officewin01_8_f | sw_roof_tar01_s | sf_gsliver07_4_f |
| Hotel | 174 | 20.0 | 39.052 | ef_union_hotel01_doorside_8_f | ef_union_hotel01_win_8_f, sw_stc_cream_pediment_f | sw_roof_tar01_s | sf_gsliver07_4_f |

