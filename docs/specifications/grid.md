# Specification — grid domain

Requirements specific to the `it-grid` domain (`src/celine/dt/domains/grid/`). The generic
values machinery is specified in [values.md](values.md); this document constrains what the
grid fetchers themselves must do.

---

## Risk exposure in km (`risk_km`)

### REQ-1300 — The `it-grid` domain MUST register a `risk_km` value fetcher over `grid_risk_km` whose row limit covers seven dates at tratta grain.

The gold table holds one row per date × vector × operational unit × tratta (about 1.3k
rows per date and vector); seven dates for both vectors is under 20 000 rows.

### REQ-1301 — `risk_km` MUST return the grain named by `level`: `tratta` rows as stored, `line` rows aggregated per `line_name`, `unit` rows aggregated per `operational_unit`; absent, `level` MUST default to `tratta`.

Aggregated rows carry the summed km columns, the worst level across the group and a
`risk_index` recomputed from the summed km, so a rollup never averages indices.

### REQ-1302 — Every optional filter of `risk_km` (`risk_vector`, `operational_unit`, `line_name`, `substation_name`, `min_level`) MUST constrain the query only when supplied.

`min_level` keeps rows whose worst level is at or above it (`WARNING` keeps `WARNING` and
`ALERT`; `ALERT` keeps `ALERT` only). At `line` and `unit` grain it is applied to the
aggregated worst level, so the km totals of a kept group are still the whole group.

### REQ-1303 — `risk_km` MUST reject a payload without `dates`, with a malformed date, or with a `level` outside `tratta | line | unit`.

## Tree-strike exposure spans (`tree_strike_spans`)

### REQ-1304 — The `it-grid` domain MUST register a `tree_strike_spans` value fetcher over `grid_tree_strike_spans` returning each span's properties and its GeoJSON feature, with a row limit covering the whole overlay.

The overlay is about 3.6k spans; the limit MUST admit all of them in one page so a
client that omits `tile_ids` still gets the complete layer.

### REQ-1305 — `tree_strike_spans` MUST restrict to the spans of the given `tile_ids` when supplied, and MUST return every span when they are omitted.

Tile ids are those of `grid_tile_index` (`tile_x_y`), resolved through
`grid_tree_strike_tiles`; a malformed id MUST be refused by the payload schema.

## Intra-day risks (`risks_8h`)

### REQ-1306 — The `it-grid` domain MUST register a `risks_8h` value fetcher over `grid_risks_8h` returning the same columns as `risks` plus `window_start` and `slot`, with a limit covering seven dates at three windows.

### REQ-1307 — `risks_8h` MUST require `dates`, MUST restrict to the given `slots` (0..2) when supplied, and MUST otherwise return every window of those dates; `risk_vector` filters as in `risks`.

## Thermal tier on shapes (`shapes`)

### REQ-1308 — `shapes` MUST select every thermal column of `grid_shapes` (`thermal_tier`, `thermal_margin_c`, `thermal_theta_max_c`, `thermal_insulation`, `is_asphalt`, `anno_posa`, `technology`, `m_r_critico`) and `name`, and its `asset_type` filter MUST admit `joint` alongside `ac_line_segment` and `substation`.

A joint row carries a point `feature_geojson`, a `name` of the form `Giunto <id>`, and
`thermal_tier` in `low | mid | high | unmodelled` (cables use `low | mid | high` or `NULL`
when unclassified). The other CIM line columns (`conductor_type`, `length_m`,
`strike_tree_tier`, `voltage_class`, …) stay `NULL` on a joint row: it is not a segment.

## Thermal exposure in km (`risk_km`)

### REQ-1309 — `risk_km` MUST carry `km_thermal_high` and `km_thermal_mid` at every grain: selected as stored at `tratta`, summed at `line` and `unit`.

These mirror `km_tree_high` / `km_tree_mid`: the gold table already carries the thermal
km at tratta grain, so the fetcher only needs to select them through, and to fold them
into the same `sum(...)` group used for the tree-strike and level columns at the
aggregated grains. Heat rows carry the real km; wind rows carry 0, same as the
tree-strike columns.

## Joint rows in the risk tables (`risks`, `risks_8h`, `risks_now`)

### REQ-1310 — `risks`, `risks_8h` and `risks_now` MUST return joint rows under `risk_vector = 'heat'` whose `metrics` jsonb carries `asset_type: 'joint'`.

This is a contract note, not a fetcher change: the column list of the three risk
fetchers is unchanged (`segment_id` doubles as the joint id, `metrics` is opaque JSONB),
so a joint row needs no new column, only the `asset_type` discriminator inside `metrics`
that the frontend already uses to tell a joint marker from a segment.

## Tree-strike km breakdown on shapes (`shapes`)

### REQ-1311 — `shapes` MUST select `strike_km_high`, `strike_km_mid` and `strike_km_low` from `grid_shapes` alongside `strike_tree_tier` and `strike_density_per_km`.

`strike_tree_tier` is the worst tier among the fragments of a tratta (the one that
escalates the wind risk) and, since grid 0.13.0, `strike_density_per_km` is the
length-weighted density over the whole tratta. The three km columns say how much of the
tratta sits in each tier, so a client can show "high" next to "2.3 km of 6.0" instead of
letting one short fragment read as the whole line. They are `NULL` on substations and
joints, `0` on a line with no fragment in that tier.
