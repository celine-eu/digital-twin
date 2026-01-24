# Values API

This document describes the **Values API** - a declarative data fetching system
for the CELINE Digital Twin runtime.

The Values API allows you to expose data queries as REST endpoints without
writing code, using YAML configuration.

---

## Overview

Value fetchers:
- Are configured in `config/values.yaml` or module configs
- Reference clients from `config/clients.yaml`
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

## Error Handling

### 400 Bad Request

Returned for:
- Missing required parameters
- Type coercion failures
- Schema validation failures
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