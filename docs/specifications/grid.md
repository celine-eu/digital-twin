# Specification — grid domain

Requirements specific to the `it-grid` domain (`src/celine/dt/domains/grid/`). The generic
values machinery is specified in [values.md](values.md); this document constrains what the
grid fetchers themselves must do, and which operator's network a fetch reads, and who may
name it.

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

---

## Every grid read names its operator

The entity is the network in the URL (`/grid/{network_id}` and every route under it).
Its id is the alias of the distribution operator's organisation, which is also the gold
`dso_id` of every grid row (celine-pipelines `grid.md`). The domain's callers reach it with a
service token as well as a user one, and dataset-api narrows no service account, so **which
operator's** rows a fetch reads is chosen here, by the statement.

### REQ-1312 — Every fetcher of the domain (`filters`, `tile_index`, `shapes`, `risks`, `risks_now`, `risk_km`, `tree_strike_spans`, `risks_8h`, `trendline`) MUST restrict **each** read of a grid table to `dso_id = <entity id>`, in the same statement, so that no row of another operator contributes to its answer.

Each read means each `FROM`, at every `level` of `risk_km`. The subselect of `shapes` over
`grid_tiles` and the one of `tree_strike_spans` over `grid_tree_strike_tiles` carry their own
predicate, so a tile id resolves within the entity's operator only. The network extent that
`filters` returns is the extent of the entity's shapes only, and `trendline` returns that
operator's ratio, not another's of the same day.

*Verified by: unit — for every fetcher id, the rendered statement for entity `example-dso` has a `dso_id = 'example-dso'` predicate on every grid table it reads (both subselects and all three `risk_km` grains included); a fake data client holding rows of `example-dso` and `other-dso` returns only `example-dso`'s*

### REQ-1313 — The entity id MUST reach a grid statement only through `sql_quote`: an id carrying a quote or SQL MUST stay one literal.

The entity id comes from the URL, so it is caller-supplied. A service with a grid scope may
name any network (REQ-1321), so the gate does not stop a malformed id from reaching the
statement; the quoting does.

*Verified by: unit — for every fetcher, the entity id `x' OR '1'='1` renders as the single literal `'x'' OR ''1''=''1'`, and the statement carries no second predicate*

### REQ-1314 — `GET /substations/map` MUST restrict `grid_substations` to `dso_id = <entity id>`, with the entity id rendered as one literal as in REQ-1313.

The route builds its statement in code, not from a query template, so it is covered here
separately from the fetchers.

*Verified by: unit — the statement sent to a fake data client for entity `example-dso` carries the predicate; an injection attempt in the entity id stays one literal*

---

## Who may name the network

The gate is the domain's `resolve_entity`, so it holds on every entity-scoped route: the
built-in ones (`/info`, `/summary`, `/values` on both verbs, `/simulations`, `/ontology`) and
the domain's own (`/substations/map`). It mirrors celine-grid's `grid.rego` (celine-grid
REQ-0006 – REQ-0009, REQ-0051), so a caller is judged the same at both services.

### REQ-1320 — A user MUST be admitted to a network only when one of the organisations in their token is of type `dso` and has the alias equal to the `network_id` in the path; otherwise the request MUST answer 403, MUST be recorded `denied` with the reason `network_not_owned`, and MUST NOT reach the data client.

The answer is the same whether or not the named network has any rows. No group within the
organisation is required, as in celine-grid.

*Verified by: unit — a user of `example-dso` reads `example-dso`; the same user naming `other-dso` gets 403 with the reason recorded and no call on a fake data client; a user of `example-dso` and `other-dso` reads both*

### REQ-1321 — A service account MUST be admitted to any network when its token's scopes include `grid.read` or `grid.admin`; a service account with neither MUST answer 403, MUST be recorded `denied` with the reason `grid_scope_missing`, and MUST NOT reach the data client.

A service account holds no organisation, so there is nothing for it to own a network with.
Which rows it reads is still the entity's only (REQ-1312).

*Verified by: unit — a client-credentials token with `grid.read`, one with `grid.admin`, one with another scope and one with no `scope` claim*

### REQ-1322 — A token that carries at least one organisation MUST be judged as a user under REQ-1320, whatever its username or its scopes.

Holding `grid.read` or `grid.admin` does not widen a user's reach to networks they do not
own. Judging by organisation first keeps a user token with a `scope` claim from being
evaluated under the service rule, where ownership is never checked.

*Verified by: unit — a user token of `example-dso` carrying `grid.admin` naming `other-dso` gets 403 `network_not_owned`*

### REQ-1323 — An organisation of a type other than `dso` MUST NOT admit its members to a network, even when its alias equals the `network_id`.

*Verified by: unit — a member of a `rec` organisation whose alias equals the requested `network_id` gets 403 `network_not_owned`*

### REQ-1324 — The realm role `platform-admin`, a realm group and an organisation group MUST NOT widen REQ-1320: a caller is admitted to a network only as a member of that operator's organisation.

> The Digital Twin grants no platform-wide grid access, consistent with celine-grid
> REQ-0051. Platform-wide reads remain dataset-api's to grant and to audit, on its own
> routes.

*Verified by: unit — a `platform-admin` with no `dso` organisation, and one in the `admins` group of `example-dso` naming `other-dso`, both get 403 `network_not_owned`*

### REQ-1325 — The gate MUST hold on every entity-scoped route of the domain, the domain's own routes included.

*Verified by: integration — through the application's test client, a user of `example-dso` naming `other-dso` gets 403 on `/info`, `/summary`, `/values` (GET and POST), `/simulations`, `/ontology/{spec_id}` and `/substations/map`, and one audit record each*

### REQ-1326 — Through the running services, every grid fetcher MUST answer the named operator's rows only, for the grid service's token as for a user's.

*Verified by: e2e — on a local stack whose warehouse holds grid rows of `example-dso` and `other-dso`: the grid service's client-credentials token asks each fetcher and `/substations/map` for `example-dso` and gets no row with another `dso_id`; a user of `example-dso` naming `other-dso` directly at the Digital Twin gets 403*

---

## No legacy wind and heat routes

### REQ-1330 — The domain MUST mount no route under `/wind/` or `/heat/`: every request to one answers 404, and the OpenAPI document lists no `it_grid_wind_*` or `it_grid_heat_*` operation.

The wind and heat risk data is served by the `risks`, `risks_now`, `risks_8h`, `risk_km` and
`trendline` fetchers, over tables that carry the operator. The removed routes read
intermediaries that governance does not expose and that dataset-api refuses to every caller.

*Verified by: unit — the mounted application answers 404 on `/grid/example-dso/wind/map`, `/wind/bosco`, `/wind/alert-distribution`, `/wind/trend`, `/heat/map`, `/heat/alert-distribution` and `/heat/trend`, and `/openapi.json` (dev) names none of their operation ids*
