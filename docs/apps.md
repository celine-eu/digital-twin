# Apps

This document covers **DTApp** in depth—the contract, execution model, mappers, and best practices for building Digital Twin applications.

---

## Overview

An **App** is an external-facing, self-contained operation exposed via the `/apps` API. Apps orchestrate components, fetch data, publish events, and return results.

| Characteristic | Description |
|----------------|-------------|
| **Exposure** | REST API at `/apps/{key}/run` |
| **Side Effects** | Allowed (events, state, external calls) |
| **Execution** | One-shot, request-scoped |
| **Dependencies** | Injected via `RunContext` |

---

## The DTApp Contract

Apps implement the `DTApp` protocol:

```python
from typing import ClassVar, Type
from pydantic import BaseModel
from celine.dt.contracts.app import DTApp
from celine.dt.contracts.mapper import InputMapper, OutputMapper
from celine.dt.core.context import RunContext

class MyConfig(BaseModel):
    """Input configuration for the app."""
    param: str

class MyResult(BaseModel):
    """Output from the app."""
    value: str

class MyApp(DTApp[MyConfig, MyResult]):
    # Required class attributes
    key: ClassVar[str] = "my-module.my-app"
    version: ClassVar[str] = "1.0.0"
    
    # Required type references
    config_type: Type[MyConfig] = MyConfig
    result_type: Type[MyResult] = MyResult
    
    # Optional mappers (can be None)
    input_mapper: InputMapper[MyConfig] | None = None
    output_mapper: OutputMapper[MyResult] | None = None
    
    async def run(self, config: MyConfig, context: RunContext) -> MyResult:
        """Execute the app logic."""
        return MyResult(value=f"Processed: {config.param}")
```

### Protocol Definition

```python
@runtime_checkable
class DTApp(Protocol[C, O]):
    """Digital Twin App contract."""
    
    key: ClassVar[str]           # Unique identifier
    version: ClassVar[str]       # Semantic version
    
    config_type: Type[C]         # Pydantic model for input
    result_type: Type[O]         # Pydantic model for output
    
    input_mapper: InputMapper[C] | None    # Transform API input
    output_mapper: OutputMapper[O] | None  # Transform API output
    
    async def run(self, config: C, context: RunContext) -> O:
        """Execute the app."""
        ...
```

---

## Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           App Execution Flow                                 │
│                                                                              │
│   HTTP Request                                                              │
│   POST /apps/my-app/run                                                     │
│   {"param": "value"}                                                        │
│         │                                                                    │
│         ▼                                                                    │
│   ┌─────────────────┐                                                       │
│   │  Input Mapper   │ ◄── Optional: transform API payload                   │
│   │  (if defined)   │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                 │
│            ▼                                                                 │
│   ┌─────────────────┐                                                       │
│   │    Validate     │ ◄── Pydantic validation against config_type          │
│   │  config_type    │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                 │
│            ▼                                                                 │
│   ┌─────────────────┐     ┌─────────────────┐                              │
│   │    app.run()    │────▶│   RunContext    │                              │
│   │                 │     │ - values        │                              │
│   │  Domain Logic   │     │ - state         │                              │
│   │                 │     │ - broker        │                              │
│   └────────┬────────┘     │ - request_id    │                              │
│            │              └─────────────────┘                              │
│            ▼                                                                 │
│   ┌─────────────────┐                                                       │
│   │  Output Mapper  │ ◄── Optional: transform result                       │
│   │  (if defined)   │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                 │
│            ▼                                                                 │
│   HTTP Response                                                             │
│   {"value": "Processed: value"}                                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Input and Output Models

### Defining Models

Use Pydantic models with Field descriptors:

```python
from pydantic import BaseModel, Field
from datetime import datetime

class MyAppConfig(BaseModel):
    """Configuration for my app."""
    
    community_id: str = Field(
        ...,  # Required
        description="Renewable Energy Community identifier",
        examples=["rec-folgaria"],
    )
    location: dict = Field(
        ...,
        description="Geographic coordinates",
        examples=[{"lat": 45.9, "lon": 11.1}],
    )
    window_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Forecast window in hours",
    )

class MyAppResult(BaseModel):
    """Result of my app."""
    
    indicator: str = Field(
        description="Status indicator"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score",
    )
    recommendations: list[str]
    window_start: datetime
    window_end: datetime
```

### Schema Exposure

Schemas are automatically exposed via API:

```bash
curl http://localhost:8000/apps/my-app/describe
```

```json
{
  "key": "my-app",
  "version": "1.0.0",
  "config_schema": {
    "type": "object",
    "required": ["community_id", "location"],
    "properties": {
      "community_id": {"type": "string", "description": "..."},
      "window_hours": {"type": "integer", "default": 24, "minimum": 1, "maximum": 168}
    }
  },
  "result_schema": {
    "type": "object",
    "properties": {
      "indicator": {"type": "string"},
      "confidence": {"type": "number", "minimum": 0, "maximum": 1}
    }
  }
}
```

---

## RunContext

Apps receive all dependencies via `RunContext`:

```python
async def run(self, config: MyConfig, context: RunContext) -> MyResult:
    # Data fetching via values
    weather = await context.values.fetch("weather_forecast", {
        "location": config.location,
        "hours": config.window_hours,
    })
    
    # Direct dataset queries
    historical = await context.datasets.query(
        sql="SELECT * FROM consumption WHERE community_id = :id",
        params={"id": config.community_id},
        limit=1000,
    )
    
    # State management
    state = await context.state.get(f"app-state:{config.community_id}")
    await context.state.set(f"app-state:{config.community_id}", new_state)
    
    # Event publishing (see Brokers documentation)
    if context.has_broker():
        await context.publish_event(my_event)
    
    # Request metadata
    request_id = context.request_id
    current_time = context.now
    
    # Component access
    calculator = context.get_component("energy-balance")
    balance = await calculator.compute(input_data, context)
```

### Available Context Properties

| Property | Type | Description |
|----------|------|-------------|
| `values` | `ValuesService` | Declarative data fetchers |
| `datasets` | `DatasetClient` | Direct SQL queries |
| `state` | `StateStore` | Key-value state storage |
| `broker` | `BrokerService` | Event publishing |
| `token_provider` | `TokenProvider` | Authentication tokens |
| `request_id` | `str` | Unique request identifier |
| `now` | `datetime` | Current UTC timestamp |

### Available Context Methods

| Method | Description |
|--------|-------------|
| `get_component(key)` | Get registered component |
| `has_broker()` | Check if broker is available |
| `publish_event(event)` | Publish event to broker |

---

## Mappers

Mappers transform data between API format and internal format.

### Input Mapper

Transform incoming API payload before validation:

```python
from celine.dt.contracts.mapper import InputMapper

class MyInputMapper(InputMapper[MyConfig]):
    def map(self, raw: dict) -> dict:
        # Transform external format to internal
        return {
            "community_id": raw.get("communityId"),
            "location": {
                "lat": raw.get("latitude"),
                "lon": raw.get("longitude"),
            },
            "window_hours": raw.get("hours", 24),
        }
```

### Output Mapper

Transform result before returning to caller:

```python
from celine.dt.contracts.mapper import OutputMapper

class MyOutputMapper(OutputMapper[MyResult]):
    def map(self, result: MyResult) -> dict:
        # Transform internal format to external
        return {
            "status": result.indicator,
            "score": result.confidence,
            "actions": result.recommendations,
        }
```

---

## Publishing Events

Apps can publish domain-specific events via the broker. **Each module defines its own events** in a dedicated `events.py` file.

```python
# my_module/events.py
from datetime import datetime
from pydantic import BaseModel, Field
from celine.dt.contracts.events import DTEvent, EventSource

class MyEventPayload(BaseModel):
    """Payload for my module's events."""
    community_id: str
    indicator: str
    confidence: float
    computed_at: datetime

class MyModuleEventTypes:
    """Event type constants for my module."""
    RESULT_COMPUTED = "dt.my-module.result-computed"

def create_result_event(
    *,
    community_id: str,
    indicator: str,
    confidence: float,
    app_version: str = "1.0.0",
) -> DTEvent[MyEventPayload]:
    """Factory function to create a result computed event."""
    return DTEvent[MyEventPayload](
        event_type=MyModuleEventTypes.RESULT_COMPUTED,
        source=EventSource(
            app_key="my-module.my-app",
            app_version=app_version,
            module="my-module",
        ),
        payload=MyEventPayload(
            community_id=community_id,
            indicator=indicator,
            confidence=confidence,
            computed_at=datetime.utcnow(),
        ),
    )
```

Then use in your app:

```python
# my_module/apps/my_app.py
from celine.dt.contracts.app import DTApp
from celine.dt.core.context import RunContext

# Import from YOUR module's events, not from contracts
from my_module.events import create_result_event
from my_module.models import MyConfig, MyResult

class MyApp(DTApp[MyConfig, MyResult]):
    key = "my-module.my-app"
    version = "1.0.0"
    
    config_type = MyConfig
    result_type = MyResult
    
    input_mapper = None
    output_mapper = None
    
    async def run(self, config: MyConfig, context: RunContext) -> MyResult:
        # Compute result
        result = await self._compute(config, context)
        
        # Publish event if broker is available
        if context.has_broker():
            event = create_result_event(
                community_id=config.community_id,
                indicator=result.indicator,
                confidence=result.confidence,
                app_version=self.version,
            )
            await context.publish_event(event)
        
        return result
```

> **Important**: Domain-specific events belong in your module's `events.py`, not in `celine.dt.contracts.events`. The contracts module only contains base event types and generic app lifecycle events.

---

## Registration

### Via Module

```python
class MyModule:
    name = "my-module"
    version = "1.0.0"
    
    def register(self, registry: DTRegistry) -> None:
        registry.register_app(MyApp())
        registry.register_app(AnotherApp())
```

### With Defaults

```python
registry.register_app(
    MyApp(),
    defaults={"window_hours": 48},  # Default config values
)
```

---

## API Reference

### List Apps

```http
GET /apps
```

Response:
```json
[
  {
    "key": "my-module.my-app",
    "version": "1.0.0",
    "config_schema": { ... },
    "result_schema": { ... }
  }
]
```

### Describe App

```http
GET /apps/{key}/describe
```

Response:
```json
{
  "key": "my-module.my-app",
  "version": "1.0.0",
  "defaults": {},
  "config_schema": { ... },
  "result_schema": { ... }
}
```

### Run App

```http
POST /apps/{key}/run
Content-Type: application/json

{
  "community_id": "rec-folgaria",
  "location": {"lat": 45.9, "lon": 11.1}
}
```

Response:
```json
{
  "indicator": "OPTIMAL",
  "confidence": 0.9,
  "recommendations": ["Continue normal operations."],
  "window_start": "2024-01-15T10:00:00Z",
  "window_end": "2024-01-16T10:00:00Z"
}
```

---

## Testing Apps

### Unit Test (Recommended)

```python
import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone

from my_module.apps.my_app import MyApp
from my_module.models import MyConfig

@pytest.fixture
def app():
    return MyApp()

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.now = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    context.request_id = "test-request-123"
    context.has_broker.return_value = False
    
    # Mock values service
    context.values = AsyncMock()
    context.values.fetch.return_value = [
        {"clouds_pct": 20, "temp": 15},
        {"clouds_pct": 30, "temp": 18},
    ]
    
    return context

@pytest.mark.asyncio
async def test_app_returns_result(app, mock_context):
    config = MyConfig(
        community_id="test-rec",
        location={"lat": 45.9, "lon": 11.1},
    )
    
    result = await app.run(config, mock_context)
    
    assert result.indicator in ["OPTIMAL", "SUBOPTIMAL", "CRITICAL"]
    assert 0 <= result.confidence <= 1

@pytest.mark.asyncio
async def test_app_publishes_event(app, mock_context):
    mock_context.has_broker.return_value = True
    mock_context.publish_event = AsyncMock()
    
    config = MyConfig(
        community_id="test-rec",
        location={"lat": 45.9, "lon": 11.1},
    )
    
    await app.run(config, mock_context)
    
    mock_context.publish_event.assert_called_once()
```

### Integration Test

```python
from fastapi.testclient import TestClient
from celine.dt.main import create_app

def test_app_api():
    app = create_app()
    client = TestClient(app)
    
    response = client.post(
        "/apps/my-module.my-app/run",
        json={
            "community_id": "test-rec",
            "location": {"lat": 45.9, "lon": 11.1},
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "indicator" in data
```

---

## Best Practices

### Do

- Keep `run()` focused on orchestration
- Use components for complex calculations
- Fetch data via `context.values` or `context.datasets`
- Publish events for observability
- Validate business rules in `run()`
- Return rich, typed results
- Define module-specific events in your module's `events.py`

### Don't

- Import HTTP/database libraries in app code
- Access environment variables directly
- Use global state
- Perform heavy computation in `run()` (use components)
- Hardcode configuration values
- Swallow exceptions silently
- Put domain-specific events in `celine.dt.contracts.events`

---

## Error Handling

```python
async def run(self, config: MyConfig, context: RunContext) -> MyResult:
    # Validation errors → 400 Bad Request
    if config.value < 0:
        raise ValueError("Value must be non-negative")
    
    # Not found → 404
    data = await context.values.fetch("my-data", {"id": config.id})
    if not data:
        raise KeyError(f"Data not found for id: {config.id}")
    
    # Internal errors → 500 Internal Server Error
    try:
        result = await self._compute(data)
    except Exception as e:
        raise RuntimeError(f"Computation failed: {e}") from e
    
    return result
```

---

## Next Steps

- [Components](developer-guide.md#part-2-creating-a-component) - Build reusable computation units
- [Simulations](simulations.md) - Create what-if explorations
- [Values API](values.md) - Configure data fetchers
- [Brokers](brokers.md) - Set up event publishing and subscription