# Values API

This document describes the **Values API** - a declarative data fetching system
for the CELINE Digital Twin runtime.

The Values API allows you to expose data queries as REST endpoints declaratively: a
`ValueFetcherSpec` describes the query, its input schema and its output mapping, and the
runtime mounts the endpoint.

> **Paths and declarations below are partly stale, verified against the code on
> 2026-08-15.** The *semantics* — templating, payload schemas, defaults, mappers,
> pagination — are accurate and tested. The *surface* is not:
>
> - **There is no global `/values/...` endpoint.** Fetchers are entity-scoped and mounted
>   per domain: `/{route_prefix}/{entity_id}/values/{fetcher_id}`, on port **8002**. Every
>   `curl` below showing `localhost:8000/values/...` is wrong on both counts, and all of
>   them require a bearer token.
> - **Fetchers are not declared in YAML.** There is no *config/values.yaml* and nothing
>   reads one. A domain returns `ValueFetcherSpec` objects from `get_value_specs()`; the
>   YAML block under "Quick Start" and "Configuration Reference" is the shape of that
>   dataclass, not of a file.
> - **"Module-Scoped Fetchers" is superseded.** There are no modules. Fetchers are
>   namespaced `{domain.name}.{id}` in the registry, but the URL path takes the
>   **domain-local** id.
>
> The mounted surface is `docs/domains.md`. What must hold is
> `docs/specifications/values.md` and `docs/specifications/query-templates.md`.

---

## Overview

Value fetchers:
- Are declared **in code**, by a domain's `get_value_specs()`. There is no
  *config/values.yaml*; nothing reads one
- Reference clients by key from `config/clients.yaml`, and startup fails on a key that
  file does not declare
- Support parameterized queries with `:param` syntax
- Validate inputs using JSON Schema
- Transform outputs using mappers
- Are exposed via REST API

---

## Quick Start

### 1. Define a fetcher

```yaml
# config/values.yaml
values:
  weather_forecast:
    client: dataset_api
    query: |
      SELECT * FROM weather_forecasts
      WHERE location = :location
        AND forecast_date >= :start_date
      ORDER BY forecast_date
    limit: 100
    payload:
      type: object
      required:
        - location
      properties:
        location:
          type: string
        start_date:
          type: string
          default: "2024-01-01"
```

### 2. Use the API

```bash
# GET with query parameters
curl "http://localhost:8000/values/weather_forecast?location=folgaria"

# POST with JSON body
curl -X POST http://localhost:8000/values/weather_forecast \
  -H "Content-Type: application/json" \
  -d '{"location": "folgaria", "start_date": "2024-06-01"}'
```

### 3. Response format

```json
{
  "items": [
    {"location": "folgaria", "forecast_date": "2024-06-01", "temp": 22.5},
    {"location": "folgaria", "forecast_date": "2024-06-02", "temp": 24.0}
  ],
  "limit": 100,
  "offset": 0,
  "count": 2
}
```

---

## Configuration Reference

### Fetcher specification

```yaml
values:
  <fetcher_id>:
    client: <client_name>        # Required: client from clients.yaml
    query: <query_template>      # Query with :param placeholders
    limit: <number>              # Default: 100
    offset: <number>             # Default: 0
    payload: <json_schema>       # Optional: input validation schema
    output_mapper: <import_path> # Optional: output transformation
```

### Field descriptions

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `client` | Yes | - | Client name from `config/clients.yaml` |
| `query` | No | - | Query template (SQL or client-specific) |
| `limit` | No | 100 | Default result limit |
| `offset` | No | 0 | Default pagination offset |
| `payload` | No | - | JSON Schema for input validation |
| `output_mapper` | No | - | Import path to output mapper class |

A fetcher declared in YAML always queries with the caller's token. A domain's
`get_value_specs()` may also set `identity="service"` on a `ValueFetcherSpec`, for rows that
are the same for every caller; see [Reference boundaries](#reference-boundaries).

---

## Query Templates

### Parameter syntax

Use `:param_name` for named parameters:

```yaml
query: |
  SELECT * FROM users
  WHERE department = :department
    AND status = :status
    AND created_at > :since
```

### Parameter substitution

Parameters are safely quoted based on their type:

| Type | Example | Quoted as |
|------|---------|-----------|
| String | `"hello"` | `'hello'` |
| Integer | `42` | `42` |
| Float | `3.14` | `3.14` |
| Boolean | `true` | `TRUE` |
| Null | `null` | `NULL` |
| List | `[1, 2, 3]` | `(1, 2, 3)` |

### String escaping

Single quotes in strings are escaped:

```python
# Input: {"name": "O'Brien"}
# Query: WHERE name = :name
# Result: WHERE name = 'O''Brien'
```

---

## Payload Schema

Define input validation using JSON Schema:

```yaml
payload:
  type: object
  additionalProperties: false
  required:
    - location
  properties:
    location:
      type: string
      description: Location identifier
    start_date:
      type: string
      format: date
      default: "2024-01-01"
    limit:
      type: integer
      minimum: 1
      maximum: 1000
      default: 100
    active:
      type: boolean
      default: true
```

### Supported types

| JSON Schema Type | GET coercion | Example |
|------------------|--------------|---------|
| `string` | As-is | `?name=test` → `"test"` |
| `integer` | Parse int | `?count=42` → `42` |
| `number` | Parse float | `?price=9.99` → `9.99` |
| `boolean` | true/false/1/0 | `?active=true` → `true` |
| `array` | Comma-separated | `?ids=1,2,3` → `[1,2,3]` |
| `null` | empty/"null" | `?val=` → `null` |

### Defaults

Defaults are applied for missing parameters:

```yaml
properties:
  status:
    type: string
    default: "active"  # Used if not provided
```

### Required fields

Missing required fields return 400 Bad Request:

```yaml
required:
  - location  # Must be provided
```

---

## API Endpoints

### List fetchers

```http
GET /values
```

Response:

```json
[
  {"id": "weather_forecast", "client": "dataset_api", "has_payload_schema": true},
  {"id": "ev_charging.solar", "client": "dataset_api", "has_payload_schema": false}
]
```

### Describe fetcher

```http
GET /values/{fetcher_id}/describe
```

Response:

```json
{
  "id": "weather_forecast",
  "client": "dataset_api",
  "query": "SELECT * FROM weather_forecasts WHERE location = :location",
  "limit": 100,
  "offset": 0,
  "payload_schema": {
    "type": "object",
    "required": ["location"],
    "properties": {
      "location": {"type": "string"}
    }
  },
  "has_output_mapper": false
}
```

### Fetch with GET

```http
GET /values/{fetcher_id}?param1=value1&param2=value2&limit=10&offset=0
```

- Parameters are coerced based on schema
- `limit` and `offset` are reserved for pagination
- Unknown parameters are passed through if `additionalProperties: true`

### Fetch with POST

```http
POST /values/{fetcher_id}?limit=10&offset=0
Content-Type: application/json

{"param1": "value1", "param2": 42}
```

- Body is validated against payload schema
- `limit` and `offset` can be query params

---

## Module-Scoped Fetchers

Modules can define their own fetchers, namespaced by module name.

### Definition in module config

```yaml
# config/modules.yaml
modules:
  - name: ev-charging
    version: ">=1.0.0"
    import: celine.dt.modules.ev_charging.module:module
    values:
      solar_forecast:
        client: dataset_api
        query: SELECT * FROM solar WHERE lat = :lat AND lon = :lon
        payload:
          type: object
          required: [lat, lon]
          properties:
            lat:
              type: number
            lon:
              type: number
```

### Access via API

Module fetchers are namespaced as `{module_name}.{fetcher_id}`:

```bash
curl "http://localhost:8000/values/ev-charging.solar_forecast?lat=45.9&lon=11.1"
```

### Precedence

- Root-level fetchers (from `values.yaml`) have no prefix
- Module fetchers are always prefixed
- Root-level fetchers cannot override module fetchers (different namespaces)

---

## Output Mappers

Transform results before returning:

```yaml
values:
  users:
    client: dataset_api
    query: SELECT * FROM users
    output_mapper: my.module.mappers:UserOutputMapper
```

### Mapper implementation

```python
# my/module/mappers.py
from celine.dt.contracts.mapper import OutputMapper


class UserOutputMapper(OutputMapper):
    output_type = dict

    def map(self, result: dict) -> dict:
        return {
            "userId": result["id"],
            "fullName": f"{result['first_name']} {result['last_name']}",
            "email": result["email"],
        }
```

The mapper is applied to each item in the result.

---

## Reference boundaries

Two fetchers every energy-community locale inherits from `EnergyCommunityDomain`
([ADR-0003](decisions/ADR-0003-boundary-fetchers-live-in-the-energy-community-domain.md);
requirements REQ-1150 – REQ-1159 and REQ-1214 in `specifications/`). Declared in
`src/celine/dt/domains/energy_community/boundary_fetchers.py`.

| | `boundary_at_point` | `boundary_shape` |
|---|---|---|
| Path (Italy) | `POST /communities/it/{community_id}/values/boundary_at_point` | `POST /communities/it/{community_id}/values/boundary_shape` |
| Payload | `{"source": "gse_cabine_primarie", "lat": <number -90..90>, "lon": <number -180..180>}` | `{"source": "gse_cabine_primarie", "ids": [<string 1..64 chars>, …]}`, at most 100 ids |
| Answer | `items`: `[]`, or `[{"id": "<cod_ac>"}]` | `items`: `[{"id": "<cod_ac>", "geojson": "<GeoJSON geometry, as a string>"}, …]`, sorted by `id` |
| `limit` | 1 | 100 |

- **`source` is a closed enum**, today `gse_cabine_primarie` alone: the GSE conventional
  primary-substation areas in `ds_dev_gold.gse_cabine_primarie` (`cod_ac`, `geometry` in
  EPSG:4326). Anything else, or a missing field, a coordinate out of range or not a number,
  more than 100 ids: **400**, and no statement is sent. Each value selects its table
  through a literal Jinja branch that exposes it as `(id, geometry)`; a new source is a new
  enum value and a new branch.
- **The community in the path does not scope the answer.** Boundaries are open reference
  data; any community id resolves.
- **A point on an edge is inside.** The statement uses `ST_Intersects(geometry, point)`,
  which for a point is exactly `ST_Covers` (interior or boundary). `ST_Covers` itself is
  not in dataset-api's SQL allowlist. Of several covering shapes (a shared edge or corner,
  an overlap) the answer is the lowest `id` (`ORDER BY id`, `limit` 1), the same on every
  call. No covering shape: 200 with no rows.
- **`boundary_shape`** answers one row per requested id the source knows; an unknown id is
  simply absent, and an empty `ids` answers 200 with no rows without sending a list. The
  shape is `ST_AsGeoJSON(ST_Simplify(geometry, 0.0001, TRUE), 6)`: a tolerance of 0.0001
  degrees (about 11 m north-south, 8 m east-west at 45° N) for a map, collapsed shapes
  kept, coordinates to 6 decimals. It is a display shape, not the stored boundary; a caller
  deciding containment asks `boundary_at_point`. `geojson` is a string: parse it.
- **Lexical order** is the database's `ORDER BY` on the id column. dataset-api refuses
  `COLLATE`, so for ids of one fixed shape (the GSE codes are) the order is the byte order.

**Who may call them.** The Digital Twin authenticates every entity route with a verified
JWT whose audience is `svc-digital-twin` (`src/celine/dt/core/config.py`), and checks
no scope itself. In Keycloak a client gets that audience by holding
`digital-twin.values.read`, which derives the audience mapper onto `svc-digital-twin`
(`celine-policies`' `clients.yaml`). **That scope is the whole grant on this side.**

**Whose token reaches dataset-api.** Every other fetcher forwards the caller's token, and
dataset-api narrows the rows to that caller. These two do not: they declare
`identity="service"` in their `ValueFetcherSpec`, so the executor hands the client no
request context and `DatasetSqlApiClient` authenticates with the Digital Twin's own
client-credentials token (the `dataset_api` client's `scope: dataset.query` in
`config/clients.yaml`; REQ-1125, REQ-1160). The boundaries are open reference data, so the
rows do not depend on who asks. The caller therefore needs `digital-twin.values.read` and
nothing on dataset-api: no `dataset.query`, no `svc-dataset-api` audience. The route still
requires the caller's verified token; without one it answers 401 and nothing is sent.

**No service identity configured.** The Digital Twin's own token comes from its OIDC
client-credentials provider, which is off when the OIDC settings (base URL, client id,
secret) are absent. Then a `"service"` fetcher answers **503** with
`{"detail": {"error": "service_identity_unavailable", "message": …}}` and nothing is sent to
dataset-api (REQ-1129). The same 503 answers when the provider is configured but cannot
obtain a token (the identity provider is down or refuses the client credentials); it never falls back to an unauthenticated query. `"caller"` fetchers
are unaffected. The client sends one `Bearer` scheme on every request (REQ-1128).

`identity` defaults to `"caller"`. Declare `"service"` only for a fetcher whose rows are the
same for every caller; any row filter dataset-api applies then applies to the Digital Twin,
not to the person asking.

**Privacy.** A caller's point is personal data. The fetchers select no personal data, and
the executor logs neither payload values, nor the rendered statement (a fetch is logged by
fetcher id, limit and offset; REQ-1127), nor a failed validation's value (it logs the
property and the rule). When dataset-api answers an error, the client logs its status and a
code derived from the status (`query_refused`, `unauthenticated`, `forbidden`, `not_found`,
`rate_limited`, `client_error`, `upstream_error`), never the response body, which can quote
the statement and so the point (REQ-1126). The reason is in dataset-api's log.

**Negative coordinates.** A point south of the equator or west of Greenwich renders as
signed numeric literals, `ST_Point(-0.3, -0.05)`. dataset-api's SQL allowlist admits a
unary minus on a numeric literal from its clause QE-02 on; against a dataset-api without
QE-02 such a point is refused (`Unsupported SQL construct: Neg`) and surfaces here as a
500. Every point of the one enabled source (Italy) is positive.

---

## Error Handling

### 400 Bad Request

Returned for:
- Missing required parameters
- Type coercion failures
- Schema validation failures
- A NaN or infinite number anywhere in the payload of a fetcher that declares a
  `payload_schema` (JSON Schema's `number` admits NaN and NaN passes every
  `minimum`/`maximum`, so the executor refuses it itself; the message names the property,
  not the value)
- Missing query parameters

```json
{
  "detail": "Missing required parameter: 'location'"
}
```

### 404 Not Found

Returned when fetcher doesn't exist:

```json
{
  "detail": "Fetcher 'nonexistent' not found"
}
```

### 500 Internal Server Error

Returned for:
- Client query failures
- Output mapper errors
- Unexpected exceptions

### 503 Service Unavailable

Returned by a fetcher declared with `identity="service"` (the
[reference boundaries](#reference-boundaries)) when the Digital Twin has no service
identity configured, or its identity provider does not give it a token. Nothing is sent to
dataset-api.

```json
{
  "detail": {"error": "service_identity_unavailable", "message": "The Digital Twin has no service identity configured"}
}
```

---

## Best Practices

### 1. Use meaningful IDs

```yaml
# Good
values:
  weather_forecast_hourly:
  energy_production_daily:

# Avoid
values:
  data1:
  query2:
```

### 2. Always define payload schemas

Even for simple fetchers, schemas provide:
- Input validation
- Type coercion for GET requests
- Self-documenting API via `/describe`

### 3. Set appropriate limits

```yaml
values:
  large_dataset:
    client: dataset_api
    query: SELECT * FROM events
    limit: 100  # Reasonable default, not 10000
```

### 4. Use defaults for optional parameters

```yaml
payload:
  properties:
    status:
      type: string
      default: "active"  # Sensible default
    days:
      type: integer
      default: 7
```

### 5. Document with descriptions

```yaml
payload:
  type: object
  properties:
    location:
      type: string
      description: "Location identifier (e.g., 'folgaria', 'trento')"
    window_hours:
      type: integer
      description: "Forecast window in hours"
      minimum: 1
      maximum: 168
```

### 6. Prefer POST for complex queries

- GET is great for simple queries with few parameters
- POST is better for complex payloads or sensitive data

---

## Examples

### Simple lookup

```yaml
values:
  location_info:
    client: dataset_api
    query: SELECT * FROM locations WHERE id = :id
    payload:
      type: object
      required: [id]
      properties:
        id:
          type: string
```

### Time-range query

```yaml
values:
  energy_readings:
    client: dataset_api
    query: |
      SELECT timestamp, value, unit
      FROM energy_readings
      WHERE meter_id = :meter_id
        AND timestamp >= :start
        AND timestamp < :end
      ORDER BY timestamp
    limit: 1000
    payload:
      type: object
      required: [meter_id, start, end]
      properties:
        meter_id:
          type: string
        start:
          type: string
          format: date-time
        end:
          type: string
          format: date-time
```

### Aggregation query

```yaml
values:
  daily_summary:
    client: dataset_api
    query: |
      SELECT 
        date_trunc('day', timestamp) as day,
        SUM(value) as total,
        AVG(value) as average
      FROM readings
      WHERE location = :location
        AND timestamp >= :since
      GROUP BY 1
      ORDER BY 1
    payload:
      type: object
      required: [location]
      properties:
        location:
          type: string
        since:
          type: string
          format: date
          default: "2024-01-01"
```

### Multi-value filter

```yaml
values:
  filtered_items:
    client: dataset_api
    query: |
      SELECT * FROM items
      WHERE category IN :categories
        AND status = :status
    payload:
      type: object
      required: [categories]
      properties:
        categories:
          type: array
          items:
            type: string
        status:
          type: string
          default: "active"
```

Usage:

```bash
# GET with comma-separated array
curl "http://localhost:8000/values/filtered_items?categories=a,b,c"

# POST with JSON array
curl -X POST http://localhost:8000/values/filtered_items \
  -d '{"categories": ["a", "b", "c"]}'
```
