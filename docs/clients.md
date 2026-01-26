# Clients Configuration

This document describes how to configure **data clients** in the CELINE Digital Twin runtime.

Clients are pluggable data backends that can be used by apps and value fetchers
to access external data sources.

---

## Overview

Clients are configured in `config/clients.yaml` and:
- Are dynamically loaded at startup
- Can receive injected services (e.g., token providers)
- Are registered in the `ClientsRegistry`
- Are accessible by name from value fetchers

---

## Configuration File

Create or edit `config/clients.yaml`:

```yaml
clients:
  dataset_api:
    class: celine.dt.core.datasets.dataset_api:DatasetSqlApiClient
    inject:
      - token_provider
    config:
      base_url: "${DATASET_API_URL:-http://localhost:8001}"
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
| `inject` | No | List of services to inject from app state |
| `config` | No | Configuration dict passed to client constructor |

---

## Environment Variable Substitution

Configuration values support environment variable substitution:

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

Clients can receive services from the application state via the `inject` list.

Currently available injectable services:

| Service | Description |
|---------|-------------|
| `token_provider` | OIDC token provider for authenticated requests |

Example:

```yaml
clients:
  authenticated_api:
    class: my.module:AuthenticatedClient
    inject:
      - token_provider
    config:
      base_url: "${API_URL}"
```

The client class must accept `token_provider` as a constructor argument:

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

For SQL-based data sources, implement the `DatasetClient` protocol:

```python
# my/module/client.py
from typing import Any, AsyncIterator
from celine.dt.core.datasets.client import DatasetClient


class MyCustomClient(DatasetClient):
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
    ) -> list[dict[str, Any]]:
        # Implement your query logic
        ...

    def stream(
        self,
        *,
        sql: str,
        page_size: int = 1000,
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

```yaml
values:
  my_data:
    client: my_client  # References the client name
    query: SELECT * FROM data WHERE id = :id
```

---

## Non-SQL Clients

Clients don't have to be SQL-based. The `query` field in value fetchers
can be any client-specific format.

Example for a REST API client:

```python
class RestApiClient:
    async def query(self, *, sql: str, limit: int, offset: int):
        # 'sql' could be a URL path or JSON query
        # Parse and execute accordingly
        ...
```

```yaml
values:
  users:
    client: rest_api
    query: /users?status=active  # Not SQL, but client understands it
```

---

## Multiple Files

Client configurations can be split across multiple files using glob patterns:

```python
# In settings
clients_config_paths: List[str] = [
    "config/clients.yaml",
    "config/clients/*.yaml",
]
```

Later files override earlier ones when client names collide.

---

## Verifying Configuration

### Check loaded clients at startup

The runtime logs loaded clients:

```
INFO - Loaded 2 client specification(s): ['dataset_api', 'weather_api']
INFO - Registered client: dataset_api
INFO - Registered client: weather_api
```

### Runtime access

Clients are available on `app.state`:

```python
# In API handlers
client = request.app.state.dataset_api

# Or via registry
client = request.app.state.clients_registry.get("dataset_api")
```

---

## Error Handling

### Missing environment variable

```
ValueError: Client 'my_client' config error: Environment variable 'API_URL' 
is not set and no default provided
```

**Solution**: Set the environment variable or provide a default.

### Missing injectable service

```
ValueError: Client 'my_client' requires injectable service 'token_provider' 
but it was not provided
```

**Solution**: Ensure OIDC is configured if using `token_provider`.

### Invalid class path

```
ImportError: Cannot import module 'nonexistent.module'
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
