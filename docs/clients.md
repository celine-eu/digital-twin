# Clients Configuration

This document describes how to configure **data clients** in the CELINE Digital Twin runtime.

Clients are pluggable data backends that can be used by apps and value fetchers
to access external data sources.

---

## Overview

Clients are configured in `config/clients.yaml` and:
- Are dynamically loaded at startup
- Receive the Digital Twin's token provider when their constructor takes one
- Are registered in the `ClientsRegistry`
- Are accessible by name from value fetchers
- Are accessible from domain and event handlers through the registry

---

## Configuration File

Create or edit `config/clients.yaml`:

```yaml
clients:
  dataset_api:
    class: celine.dt.core.clients.dataset_api:DatasetSqlApiClient
    scope: dataset.query
    config:
      base_url: "${DATASET_API_BASE_URL:-http://host.docker.internal:8001}"
      timeout: 30.0

  weather_api:
    class: my.module.weather:WeatherClient
    config:
      api_key: "${WEATHER_API_KEY}"
      base_url: "https://api.weather.example.com"
```

---

## Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `class` | Yes | Import path to the client class (`module:ClassName`) |
| `scope` | No | The scope the Digital Twin's own client-credentials token is requested with, for this client |
| `config` | No | Configuration dict passed to the client constructor as keyword arguments |

**The token provider is injected by signature.** A client whose constructor takes
`token_provider` receives the Digital Twin's OIDC client-credentials provider (client
`svc-digital-twin`, secret `CELINE_OIDC_CLIENT_SECRET`), requesting the client's `scope`
when one is given. There is no `inject` key; one in a file is ignored.

**Whose token reaches `dataset-api`.** `DatasetSqlApiClient` forwards the caller's token
when a fetcher passes the request context, which is the default. A fetcher declared
`identity="service"` passes none, and the client then authenticates with that provider's
token; with no provider, or one that cannot get a token, it sends nothing and the route
answers 503 `service_identity_unavailable` ([values.md](values.md#reference-boundaries),
REQ-1125, REQ-1129).

---

## Environment Variable Substitution

Values under `config` support environment variable substitution (`class` and `scope`
are read as written):

| Syntax | Behavior |
|--------|----------|
| `${VAR}` | Required - startup fails if not set |
| `${VAR:-default}` | Optional - uses default value if not set |

Example:

```yaml
clients:
  my_client:
    class: my.module:Client
    config:
      url: "${API_URL}"                    # Required
      timeout: "${TIMEOUT:-30}"            # Optional with default
      debug: "${DEBUG_MODE:-false}"        # Optional with default
```

---

## Dependency Injection

The one injected service is `token_provider`, the Digital Twin's OIDC client-credentials
provider. It is injected by signature, not by a YAML key: a client class that accepts
`token_provider` as a constructor argument receives it, scoped to the client's `scope`.

```yaml
clients:
  authenticated_api:
    class: my.module:AuthenticatedClient
    scope: my-service.read
    config:
      base_url: "${API_URL}"
```

```python
class AuthenticatedClient:
    def __init__(
        self,
        base_url: str,
        token_provider: TokenProvider | None = None,
    ):
        self.base_url = base_url
        self.token_provider = token_provider
```

---

## Creating a Custom Client

### 1. Implement the client class

There is no base class or protocol to inherit: a client is any class the value executor
can call as `await client.query(sql=..., limit=..., offset=..., ctx=...)`. `ctx` is the
request context (the caller's token is `ctx.token`), or `None` for a fetcher declared
`identity="service"`. `DatasetSqlApiClient` (`src/celine/dt/core/clients/dataset_api.py`)
is the reference implementation:

```python
# my/module/client.py
from typing import Any, AsyncIterator


class MyCustomClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        token_provider=None,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.token_provider = token_provider

    async def query(
        self,
        *,
        sql: str,
        limit: int = 1000,
        offset: int = 0,
        ctx=None,
    ) -> list[dict[str, Any]]:
        # Implement your query logic
        ...

    def stream(
        self,
        *,
        sql: str,
        page_size: int = 1000,
        ctx=None,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        # Implement streaming logic
        ...
```

### 2. Register in configuration

```yaml
clients:
  my_client:
    class: my.module.client:MyCustomClient
    config:
      base_url: "${MY_API_URL}"
      timeout: 60.0
```

### 3. Use in value fetchers

Fetchers are declared in a domain's `get_value_specs()` ([values.md](values.md)):

```python
ValueFetcherSpec(
    id="my_data",
    client="my_client",  # References the client name
    query="SELECT * FROM data WHERE id = :id",
    payload_schema={"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}},
)
```

---

## Non-SQL Clients

Clients don't have to be SQL-based. The `query` field in value fetchers
can be any client-specific format.

Example for a REST API client:

```python
class RestApiClient:
    async def query(self, *, sql: str, limit: int, offset: int, ctx=None):
        # 'sql' is the rendered query: it could be a URL path or JSON query
        # Parse and execute accordingly
        ...
```

```python
ValueFetcherSpec(
    id="users",
    client="rest_api",
    query="/users?status=active",  # Not SQL, but client understands it
)
```

The query is still rendered by the template engine, so `:name` and `{{ }}` keep their
meaning ([values.md](values.md#query-templates)).

---

## Multiple Files

Client configurations can be split across multiple files using glob patterns. The
setting is `clients_config_paths` in `src/celine/dt/core/config.py` (default
`["config/clients.yaml"]`), overridable with the `CLIENTS_CONFIG_PATHS` environment
variable as a JSON list:

```bash
CLIENTS_CONFIG_PATHS='["config/clients.yaml", "config/clients/*.yaml"]'
```

Matching files are loaded in sorted path order. A client name may be declared only once:
a second declaration fails startup with `ValueError: Client '<name>' already registered`.

---

## Verifying Configuration

### Check loaded clients at startup

The runtime logs each registered client, then the list (for the example file above):

```
INFO - Registered client: dataset_api (DatasetSqlApiClient)
INFO - Registered client: weather_api (WeatherClient)
INFO - Registered 2 client(s): ['dataset_api', 'weather_api']
```

### Runtime access

Clients live in the `ClientsRegistry` on the shared infrastructure:

```python
# In API handlers
client = request.app.state.infra.clients_registry.get("dataset_api")

# In event handlers
client = ctx.infra.clients_registry.get("dataset_api")
```

`get` raises `KeyError` naming the available clients for an unknown name.

---

## Nudging Client

The Digital Twin uses a dedicated client to forward enriched events to the
`nudging-tool`.

Current configuration in `config/clients.yaml`:

```yaml
nudging_admin_client:
  class: celine.sdk.nudging.client:NudgingAdminClient
  scope: "nudging.ingest"
  config:
    base_url: "${NUDGING_URL:-http://host.docker.internal:8016}"
    timeout: 5.0
```

Typical runtime usage from a participant nudging handler:

```python
nudging_admin_client: NudgingAdminClient = ctx.infra.clients_registry.get(
    "nudging_admin_client"
)
await nudging_admin_client.ingest_event(DigitalTwinEvent.from_dict(payload))
```

The current Digital Twin use case is meter transmission anomaly notifications
(`src/celine/dt/domains/participant/nudging/meters.py`), which first look up the
affected assets through the `rec_registry_admin` client
(`celine.sdk.rec_registry:RecRegistryAdminClient`, scope `rec-registry.lookup`,
`REC_REGISTRY_URL`).

---

## Error Handling

### Missing environment variable

```
ValueError: Environment variable 'API_URL' not set, no default provided
```

**Solution**: Set the environment variable or provide a default.

### No client credentials

```
INFO - No OIDC base_url configured — token provider disabled
WARNING - OIDC base_url set but client_id/client_secret missing — token provider disabled
```

The clients are still registered, with no token provider. Fetchers that forward the
caller's token work; a `"service"` fetcher answers 503 `service_identity_unavailable` and
sends nothing.

**Solution**: Configure the Digital Twin's own OIDC client (`CELINE_OIDC_BASE_URL` and
`CELINE_OIDC_CLIENT_SECRET`).

### Invalid class path

```
ImportError: Cannot import module 'nonexistent.module'
AttributeError: Module 'my.module' has no attribute 'MissingClient'
```

**Solution**: Verify the class path is correct and the module is installed.

---

## Best Practices

1. **Use environment variables** for sensitive data (API keys, secrets)
2. **Provide defaults** for non-sensitive configuration
3. **Keep clients stateless** when possible
4. **Implement proper error handling** in client methods
5. **Add logging** for debugging and monitoring
6. **Test clients independently** before integration
