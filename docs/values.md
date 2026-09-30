# Values API

This document describes the **Values API** - a declarative data fetching system
for the CELINE Digital Twin runtime.

The Values API allows you to expose data queries as REST endpoints declaratively: a
`ValueFetcherSpec` (`src/celine/dt/contracts/values.py`) describes the query, its input
schema and its pagination defaults, and the runtime mounts the endpoint under every
domain's entity scope.

What must hold is `docs/specifications/values.md` and
`docs/specifications/query-templates.md`. The full mounted surface is `docs/domains.md`.

---

## Overview

Value fetchers:
- Are declared **in code**, by a domain's `get_value_specs()`. There is no
  *config/values.yaml*; nothing reads one
- Are registered at startup as `{domain.name}.{id}`, and addressed in the URL by the
  **domain-local** `id`
- Reference clients by key from `config/clients.yaml`, and startup fails on a key that
  file does not declare
- Render their query with Jinja2 for structure, then substitute `:param` bind parameters
  for values
- Validate inputs using JSON Schema
- Are exposed via REST API, entity-scoped:
  `/{route_prefix}/{entity_id}/values/{fetcher_id}`, bearer token required

---

## Quick Start

### 1. Define a fetcher

```python
# src/celine/dt/domains/<your_domain>/domain.py
from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.domain.base import DTDomain


class MyDomain(DTDomain):
    ...

    def get_value_specs(self) -> list[ValueFetcherSpec]:
        return [
            ValueFetcherSpec(
                id="weather_forecast",
                client="dataset_api",
                query="""
                    SELECT * FROM weather_forecasts
                    WHERE location = :location
                      AND forecast_date >= :start_date
                    ORDER BY forecast_date
                """,
                limit=100,
                payload_schema={
                    "type": "object",
                    "required": ["location"],
                    "properties": {
                        "location": {"type": "string"},
                        "start_date": {"type": "string", "default": "2024-01-01"},
                    },
                },
            ),
        ]
```

### 2. Use the API

The service listens on port 8002. For a domain mounted at `/communities/it`:

```bash
# GET with query parameters
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8002/communities/it/rec-1/values/weather_forecast?location=example-location"

# POST with JSON body: the parameters go under "payload"
curl -X POST http://localhost:8002/communities/it/rec-1/values/weather_forecast \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"payload": {"location": "example-location", "start_date": "2024-06-01"}}'
```

### 3. Response format

```json
{
  "items": [
    {"location": "example-location", "forecast_date": "2024-06-01", "temp": 22.5},
    {"location": "example-location", "forecast_date": "2024-06-02", "temp": 24.0}
  ],
  "limit": 100,
  "offset": 0,
  "count": 2
}
```

`count` is the number of rows in `items`, not a total.

---

## Specification Reference

### `ValueFetcherSpec`

A frozen dataclass:

```python
@dataclass(frozen=True)
class ValueFetcherSpec:
    id: str                                   # domain-local id
    client: str                               # client key from config/clients.yaml
    query: str | None = None                  # Jinja2 + :param template
    limit: int = 100
    offset: int = 0
    payload_schema: dict[str, Any] | None = None
    output_mapper: str | None = None
    identity: Literal["caller", "service"] = "caller"
```

### Field descriptions

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `id` | Yes | - | Domain-local id; registered as `{domain.name}.{id}` |
| `client` | Yes | - | Client name from `config/clients.yaml` |
| `query` | No | - | Query template (SQL or client-specific); a fetcher with none sends `""` |
| `limit` | No | 100 | Default result limit |
| `offset` | No | 0 | Default pagination offset |
| `payload_schema` | No | - | JSON Schema for input validation |
| `output_mapper` | No | - | Import path to an output mapper; see [Output mappers](#output-mappers) |
| `identity` | No | `"caller"` | `"service"` queries with the Digital Twin's own token; see [Reference boundaries](#reference-boundaries) |

A fetcher queries with the caller's token unless it sets `identity="service"`, which is
for rows that are the same for every caller.

---

## Query Templates

A query is rendered in two passes (`src/celine/dt/core/values/template.py`):

1. **Jinja2, for structure.** The template sees `entity` (the resolved `EntityInfo`:
   `id`, `domain_name`, `metadata`) and every validated payload property by name.
2. **Bind parameters, for values.** Each `:param_name` outside a quoted literal is
   replaced by the quoted payload value.

### Parameter syntax

Use `:param_name` for named parameters:

```sql
SELECT * FROM users
WHERE department = :department
  AND status = :status
  AND created_at > :since
```

A `::` cast (`::date`, `:since::timestamp`) is not a parameter. A `:name` inside a
single-quoted literal or a double-quoted identifier is left as text. A parameter absent
from the payload fails the render (500), so declare every `:param` in the
`payload_schema`, with a default when it is optional.

### Parameter substitution

Parameters are quoted based on their type:

| Type | Example | Quoted as |
|------|---------|-----------|
| String | `"hello"` | `'hello'` |
| Integer | `42` | `42` |
| Float | `3.14` | `3.14` |
| Boolean | `true` | `TRUE` |
| Null | `null` | `NULL` |

A NaN or infinite number has no SQL literal and is refused. Anything else (a list
included) is rendered as a string literal: use `sql_list` for lists.

### String escaping

Single quotes in strings are escaped:

```python
# Input: {"name": "O'Brien"}
# Query: WHERE name = :name
# Result: WHERE name = 'O''Brien'
```

### Jinja structure and filters

Use Jinja for optional clauses and entity context; pass payload values through a filter
whenever they are interpolated with `{{ }}`:

```sql
SELECT * FROM readings
WHERE community = {{ entity.id | sql_quote }}
{% if categories %}
  AND category IN {{ categories | sql_list }}
{% endif %}
```

| Filter | Renders |
|---|---|
| `sql_quote` | one value, quoted as in the table above |
| `sql_list` | a non-empty list as `(v1, v2, …)`, each element as `sql_quote` renders it; an empty list or a non-list raises |

An undefined name is falsy in `{% if %}` and raises when interpolated. A template error
fails the render (500).

---

## Payload Schema

Define input validation using JSON Schema:

```python
payload_schema = {
    "type": "object",
    "additionalProperties": False,
    "required": ["location"],
    "properties": {
        "location": {"type": "string", "description": "Location identifier"},
        "start_date": {"type": "string", "format": "date", "default": "2024-01-01"},
        "active": {"type": "boolean", "default": True},
    },
}
```

`limit` and `offset` are taken out of the payload before validation, so a schema does
not declare them.

### GET parameters are strings

The GET route does **not** coerce query parameters by schema. Every value arrives as a
string, and a key given more than once arrives as a list of strings:

| Query string | Payload |
|---|---|
| `?name=test` | `{"name": "test"}` |
| `?count=42` | `{"count": "42"}` — fails an `integer` schema (400) |
| `?ids=a&ids=b` | `{"ids": ["a", "b"]}` |
| `?ids=a,b` | `{"ids": "a,b"}` |

Use POST for numbers, booleans, `null` and arrays.

### Defaults

Defaults of top-level `properties` are applied for missing parameters, before
validation, without modifying the caller's payload:

```python
"properties": {
    "status": {"type": "string", "default": "active"},  # used if not provided
}
```

### Required fields

Missing required fields return 400 Bad Request:

```python
"required": ["location"]  # must be provided
```

A fetcher with no `payload_schema` accepts any payload.

---

## API Endpoints

All paths are under `/{route_prefix}/{entity_id}` and require a bearer token (401
without). An entity the domain's `resolve_entity` rejects answers 404.

### List fetchers

```http
GET .../values
```

Every registered fetcher, **of every domain** (the registry is shared), with its
namespaced id:

```json
[
  {
    "id": "it-energy-community.weather_forecast",
    "spec": {
      "id": "it-energy-community.weather_forecast",
      "client": "dataset_api",
      "query": "",
      "limit": 100,
      "offset": 0,
      "payload_schema": {"type": "object", "required": ["location"], "properties": {"location": {"type": "string"}}},
      "output_mapper": null
    }
  }
]
```

`spec.query` is always `""`: the statement is not exposed.

### Describe fetcher

```http
GET .../values/{fetcher_id}/describe
```

One entry of the same shape as the list, for the domain-local `fetcher_id`.

### Fetch with GET

```http
GET .../values/{fetcher_id}?param1=value1&param2=value2&limit=10&offset=0
```

- Parameters arrive as strings; see [GET parameters are strings](#get-parameters-are-strings)
- `limit` and `offset` are reserved for pagination (integers ≥ 0, else 422)
- Other parameters are passed through unless the schema sets `additionalProperties: false`

### Fetch with POST

```http
POST .../values/{fetcher_id}
Content-Type: application/json

{"payload": {"param1": "value1", "param2": 42, "limit": 10, "offset": 0}}
```

- The body must be an object with a `payload` object (else 422)
- `limit` and `offset` are read from `payload`, not from the query string
- The rest of `payload` is validated against the payload schema

---

## Output Mappers

`FetcherDescriptor` (`src/celine/dt/core/values/executor.py`) may carry an
`output_mapper`: any object with a `map(row: dict) -> dict` method. The executor applies
it to every returned row, and a failing mapper fails the whole fetch (500) rather than
returning partial results.

```python
class UserOutputMapper:
    def map(self, row: dict) -> dict:
        return {
            "userId": row["id"],
            "fullName": f"{row['first_name']} {row['last_name']}",
        }
```

**`ValueFetcherSpec.output_mapper` is not resolved.** Startup registers each domain
fetcher as `FetcherDescriptor(spec=..., client=...)` with no mapper, so the import path
on the spec is carried and listed but never applied. No shipped fetcher declares one.

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

The payload goes in the POST body as `{"payload": {...}}`.

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
client-credentials provider (client `svc-digital-twin`, secret `CELINE_OIDC_CLIENT_SECRET`),
which is off when `CELINE_OIDC_BASE_URL` is set empty (its default is a local Keycloak
realm). Then a `"service"` fetcher answers **503** with
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

Returned for a payload that fails the fetcher's `payload_schema`:
- Missing required parameters
- Wrong types (including a GET number, which arrives as a string)
- Any other schema validation failure
- A NaN or infinite number anywhere in the payload of a fetcher that declares a
  `payload_schema` (JSON Schema's `number` admits NaN and NaN passes every
  `minimum`/`maximum`, so the executor refuses it itself; the message names the property,
  not the value)

```json
{
  "detail": {
    "error": "validation_error",
    "message": "Payload validation failed: 'location' is a required property",
    "errors": ["'location' is a required property"]
  }
}
```

### 401 Unauthorized

No bearer token: `{"detail": "Authentication required"}`.

### 404 Not Found

Returned when the fetcher doesn't exist in the entity's domain (fetch by either verb,
and describe), or the domain does not resolve the entity:

```json
{
  "detail": "Value fetcher 'nonexistent' not found"
}
```

### 422 Unprocessable Entity

A POST body without a `payload` object, or a GET `limit`/`offset` that is not an integer
≥ 0.

### 500 Internal Server Error

Returned as `{"detail": "Internal server error"}` for:
- A bind parameter absent from the payload, or any other template rendering error
- Client query failures (dataset-api refusing the statement included)
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

```python
# Good
ValueFetcherSpec(id="weather_forecast_hourly", ...)
ValueFetcherSpec(id="energy_production_daily", ...)

# Avoid
ValueFetcherSpec(id="data1", ...)
ValueFetcherSpec(id="query2", ...)
```

### 2. Always define payload schemas

Even for simple fetchers, schemas provide:
- Input validation
- Defaults for optional bind parameters
- Self-documenting API via `/describe`

### 3. Set appropriate limits

A `limit` must cover the widest window the payload schema permits, at the table's
actual granularity (REQ-1140): dataset-api caps at 10 000 and applies `LIMIT` after
`ORDER BY`, so a short limit silently drops the last rows.

```python
ValueFetcherSpec(
    id="large_dataset",
    client="dataset_api",
    query="SELECT * FROM events",
    limit=100,  # Reasonable default, not 10000
)
```

### 4. Use defaults for optional parameters

```python
"properties": {
    "status": {"type": "string", "default": "active"},  # Sensible default
    "days": {"type": "integer", "default": 7},
}
```

### 5. Document with descriptions

```python
"properties": {
    "location": {
        "type": "string",
        "description": "Location identifier (e.g., 'site-a', 'site-b')",
    },
    "window_hours": {
        "type": "integer",
        "description": "Forecast window in hours",
        "minimum": 1,
        "maximum": 168,
    },
}
```

### 6. Prefer POST for typed or complex payloads

- GET suits a few string parameters
- POST carries numbers, booleans, arrays and sensitive data as JSON

---

## Examples

### Simple lookup

```python
ValueFetcherSpec(
    id="location_info",
    client="dataset_api",
    query="SELECT * FROM locations WHERE id = :id",
    payload_schema={
        "type": "object",
        "required": ["id"],
        "properties": {"id": {"type": "string"}},
    },
)
```

### Time-range query

```python
ValueFetcherSpec(
    id="energy_readings",
    client="dataset_api",
    query="""
        SELECT timestamp, value, unit
        FROM energy_readings
        WHERE meter_id = :meter_id
          AND timestamp >= :start
          AND timestamp < :end
        ORDER BY timestamp
    """,
    limit=1000,
    payload_schema={
        "type": "object",
        "required": ["meter_id", "start", "end"],
        "properties": {
            "meter_id": {"type": "string"},
            "start": {"type": "string", "format": "date-time"},
            "end": {"type": "string", "format": "date-time"},
        },
    },
)
```

### Aggregation query

```python
ValueFetcherSpec(
    id="daily_summary",
    client="dataset_api",
    query="""
        SELECT
          date_trunc('day', timestamp) AS day,
          SUM(value) AS total,
          AVG(value) AS average
        FROM readings
        WHERE location = :location
          AND timestamp >= :since
        GROUP BY 1
        ORDER BY 1
    """,
    payload_schema={
        "type": "object",
        "required": ["location"],
        "properties": {
            "location": {"type": "string"},
            "since": {"type": "string", "format": "date", "default": "2024-01-01"},
        },
    },
)
```

### Multi-value filter

A list is interpolated with `sql_list`, never bound with `:param`. Declare `minItems`
or guard the filter with a Jinja branch, since `sql_list` refuses an empty list
(REQ-1235):

```python
ValueFetcherSpec(
    id="filtered_items",
    client="dataset_api",
    query="""
        SELECT * FROM items
        WHERE category IN {{ categories | sql_list }}
          AND status = :status
    """,
    payload_schema={
        "type": "object",
        "required": ["categories"],
        "properties": {
            "categories": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "status": {"type": "string", "default": "active"},
        },
    },
)
```

Usage:

```bash
# GET with a repeated key (a single key would arrive as a string, not a list)
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8002/communities/it/rec-1/values/filtered_items?categories=a&categories=b"

# POST with JSON array
curl -X POST http://localhost:8002/communities/it/rec-1/values/filtered_items \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"payload": {"categories": ["a", "b", "c"]}}'
```
