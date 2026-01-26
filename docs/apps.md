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

class EVChargingConfig(BaseModel):
    """Configuration for EV charging readiness assessment."""
    
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
    pv_capacity_kw: float = Field(
        ...,
        gt=0,
        description="Total PV capacity in kW",
    )
    ev_charging_capacity_kw: float = Field(
        ...,
        gt=0,
        description="Total EV charging capacity in kW",
    )

class EVChargingResult(BaseModel):
    """Result of EV charging readiness assessment."""
    
    indicator: str = Field(
        description="Readiness indicator: OPTIMAL, SUBOPTIMAL, or CRITICAL"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score",
    )
    expected_pv_kwh: float
    pv_ev_ratio: float
    recommendations: list[str]
    window_start: datetime
    window_end: datetime
```

### Schema Exposure

Schemas are automatically exposed via API:

```bash
curl http://localhost:8000/apps/ev-charging-readiness/describe
```

```json
{
  "key": "ev-charging-readiness",
  "version": "1.1.0",
  "config_schema": {
    "type": "object",
    "required": ["community_id", "location", "pv_capacity_kw", "ev_charging_capacity_kw"],
    "properties": {
      "community_id": {"type": "string", "description": "..."},
      "window_hours": {"type": "integer", "default": 24, "minimum": 1, "maximum": 168}
    }
  },
  "result_schema": {
    "type": "object",
    "properties": {
      "indicator": {"type": "string", "enum": ["OPTIMAL", "SUBOPTIMAL", "CRITICAL"]},
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
    
    # Event publishing
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

class CamelCaseInputMapper(InputMapper[MyConfig]):
    """Convert camelCase API input to snake_case config."""
    
    input_type = MyConfig
    
    def map(self, raw: dict) -> MyConfig:
        # Transform keys
        transformed = {
            "community_id": raw.get("communityId"),
            "window_hours": raw.get("windowHours", 24),
            "pv_capacity_kw": raw.get("pvCapacityKw"),
        }
        return MyConfig.model_validate(transformed)
```

### Output Mapper

Transform result before sending to API:

```python
from celine.dt.contracts.mapper import OutputMapper

class CamelCaseOutputMapper(OutputMapper[MyResult]):
    """Convert snake_case result to camelCase API output."""
    
    output_type = MyResult
    
    def map(self, result: MyResult) -> dict:
        return {
            "indicator": result.indicator,
            "confidenceScore": result.confidence,
            "expectedPvKwh": result.expected_pv_kwh,
            "recommendations": result.recommendations,
        }
```

### Wiring Mappers

```python
class MyApp(DTApp[MyConfig, MyResult]):
    key = "my-app"
    version = "1.0.0"
    
    config_type = MyConfig
    result_type = MyResult
    
    input_mapper = CamelCaseInputMapper()
    output_mapper = CamelCaseOutputMapper()
    
    async def run(self, config: MyConfig, context: RunContext) -> MyResult:
        # config is already transformed by input_mapper
        # result will be transformed by output_mapper
        ...
```

---

## Complete Example

```python
# my_module/models.py
from pydantic import BaseModel, Field
from datetime import datetime

class EVChargingConfig(BaseModel):
    community_id: str
    location: dict
    window_hours: int = Field(default=24, ge=1, le=168)
    pv_capacity_kw: float = Field(gt=0)
    ev_charging_capacity_kw: float = Field(gt=0)

class EVChargingResult(BaseModel):
    indicator: str
    confidence: float
    expected_pv_kwh: float
    pv_ev_ratio: float
    recommendations: list[str]
    window_start: datetime
    window_end: datetime
```

```python
# my_module/apps/ev_charging.py
from datetime import timedelta
from celine.dt.contracts.app import DTApp
from celine.dt.contracts.events import create_ev_charging_event
from celine.dt.core.context import RunContext

from ..models import EVChargingConfig, EVChargingResult

class EVChargingReadinessApp(DTApp[EVChargingConfig, EVChargingResult]):
    key = "ev-charging-readiness"
    version = "1.1.0"
    
    config_type = EVChargingConfig
    result_type = EVChargingResult
    
    input_mapper = None
    output_mapper = None
    
    async def run(
        self,
        config: EVChargingConfig,
        context: RunContext,
    ) -> EVChargingResult:
        # 1. Fetch weather forecast
        weather = await context.values.fetch("weather_forecast", {
            "lat": config.location["lat"],
            "lon": config.location["lon"],
            "hours": config.window_hours,
        })
        
        # 2. Compute PV generation estimate
        expected_pv_kwh = self._estimate_pv_generation(
            weather=weather,
            capacity_kw=config.pv_capacity_kw,
            hours=config.window_hours,
        )
        
        # 3. Compute ratio and indicator
        ev_demand_kwh = config.ev_charging_capacity_kw * config.window_hours
        pv_ev_ratio = expected_pv_kwh / ev_demand_kwh if ev_demand_kwh > 0 else 0
        
        indicator, confidence = self._compute_indicator(pv_ev_ratio, weather)
        recommendations = self._generate_recommendations(indicator, pv_ev_ratio)
        
        # 4. Build result
        window_start = context.now
        window_end = context.now + timedelta(hours=config.window_hours)
        
        result = EVChargingResult(
            indicator=indicator,
            confidence=confidence,
            expected_pv_kwh=expected_pv_kwh,
            pv_ev_ratio=pv_ev_ratio,
            recommendations=recommendations,
            window_start=window_start,
            window_end=window_end,
        )
        
        # 5. Publish event (optional)
        if context.has_broker():
            event = create_ev_charging_event(
                community_id=config.community_id,
                window_start=window_start,
                window_end=window_end,
                indicator=indicator,
                confidence=confidence,
                expected_pv_kwh=expected_pv_kwh,
            )
            await context.publish_event(event)
        
        return result
    
    def _estimate_pv_generation(self, weather, capacity_kw, hours) -> float:
        # Simplified estimation based on cloud cover
        avg_clouds = sum(w["clouds_pct"] for w in weather) / len(weather)
        efficiency = 1 - (avg_clouds / 100) * 0.7
        peak_sun_hours = hours * 0.4  # Rough estimate
        return capacity_kw * peak_sun_hours * efficiency
    
    def _compute_indicator(self, ratio, weather) -> tuple[str, float]:
        if ratio >= 0.8:
            return "OPTIMAL", 0.9
        elif ratio >= 0.4:
            return "SUBOPTIMAL", 0.75
        else:
            return "CRITICAL", 0.85
    
    def _generate_recommendations(self, indicator, ratio) -> list[str]:
        if indicator == "OPTIMAL":
            return ["Excellent conditions for EV charging."]
        elif indicator == "SUBOPTIMAL":
            return [
                "Consider delayed charging during peak sun hours.",
                "Prioritize critical charging sessions.",
            ]
        else:
            return [
                "Minimize charging if possible.",
                "Use off-peak grid tariffs.",
                "Defer non-essential charging.",
            ]
```

```python
# my_module/module.py
from celine.dt.core.registry import DTRegistry
from .apps.ev_charging import EVChargingReadinessApp

class EVChargingModule:
    name = "ev-charging"
    version = "1.1.0"
    
    def register(self, registry: DTRegistry) -> None:
        registry.register_app(EVChargingReadinessApp())

module = EVChargingModule()
```

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
    "key": "ev-charging-readiness",
    "version": "1.1.0",
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
  "key": "ev-charging-readiness",
  "version": "1.1.0",
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
  "location": {"lat": 45.9, "lon": 11.1},
  "pv_capacity_kw": 1200,
  "ev_charging_capacity_kw": 800
}
```

Response:
```json
{
  "indicator": "OPTIMAL",
  "confidence": 0.9,
  "expected_pv_kwh": 5100.0,
  "pv_ev_ratio": 0.27,
  "recommendations": ["Excellent conditions for EV charging."],
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

from my_module.apps.ev_charging import EVChargingReadinessApp
from my_module.models import EVChargingConfig

@pytest.fixture
def app():
    return EVChargingReadinessApp()

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
async def test_ev_charging_optimal(app, mock_context):
    config = EVChargingConfig(
        community_id="test-rec",
        location={"lat": 45.9, "lon": 11.1},
        window_hours=24,
        pv_capacity_kw=1200,
        ev_charging_capacity_kw=100,  # Low demand = optimal
    )
    
    result = await app.run(config, mock_context)
    
    assert result.indicator == "OPTIMAL"
    assert result.confidence >= 0.8
    assert result.expected_pv_kwh > 0

@pytest.mark.asyncio
async def test_ev_charging_publishes_event(app, mock_context):
    mock_context.has_broker.return_value = True
    mock_context.publish_event = AsyncMock()
    
    config = EVChargingConfig(
        community_id="test-rec",
        location={"lat": 45.9, "lon": 11.1},
        pv_capacity_kw=1200,
        ev_charging_capacity_kw=800,
    )
    
    await app.run(config, mock_context)
    
    mock_context.publish_event.assert_called_once()
```

### Integration Test

```python
from fastapi.testclient import TestClient
from celine.dt.main import create_app

def test_ev_charging_api():
    app = create_app()
    client = TestClient(app)
    
    response = client.post(
        "/apps/ev-charging-readiness/run",
        json={
            "community_id": "test-rec",
            "location": {"lat": 45.9, "lon": 11.1},
            "pv_capacity_kw": 1200,
            "ev_charging_capacity_kw": 800,
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "indicator" in data
    assert data["indicator"] in ["OPTIMAL", "SUBOPTIMAL", "CRITICAL"]
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

### Don't

- Import HTTP/database libraries in app code
- Access environment variables directly
- Use global state
- Perform heavy computation in `run()` (use components)
- Hardcode configuration values
- Swallow exceptions silently

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
- [Brokers](brokers.md) - Set up event publishing
