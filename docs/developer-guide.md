# Developer Guide

This guide shows you how to build **Apps**, **Components**, and **Simulations** for the CELINE Digital Twin. It's organized as a linear tutorial—work through it from start to finish.

---

## Prerequisites

- Python 3.11+
- Understanding of [Concepts](concepts.md)
- Familiarity with Pydantic models

---

## Part 1: Creating an App

Apps are external-facing operations exposed via `/apps` API.

### Step 1: Define Models

Create Pydantic models for input and output:

```python
# my_module/models.py
from pydantic import BaseModel, Field

class GreetingConfig(BaseModel):
    """Input configuration for the greeting app."""
    name: str = Field(..., description="Name to greet")
    formal: bool = Field(default=False, description="Use formal greeting")

class GreetingResult(BaseModel):
    """Output from the greeting app."""
    message: str
    timestamp: str
```

### Step 2: Implement the App

Apps implement the `DTApp` protocol:

```python
# my_module/apps/greeting.py
from datetime import datetime
from celine.dt.contracts.app import DTApp
from celine.dt.core.context import RunContext

from ..models import GreetingConfig, GreetingResult

class GreetingApp(DTApp[GreetingConfig, GreetingResult]):
    """A simple greeting app."""
    
    key = "my-module.greeting"
    version = "1.0.0"
    
    config_type = GreetingConfig
    result_type = GreetingResult
    
    input_mapper = None   # Optional: transform API input
    output_mapper = None  # Optional: transform API output
    
    async def run(
        self,
        config: GreetingConfig,
        context: RunContext,
    ) -> GreetingResult:
        # Domain logic only - no HTTP, no database imports
        if config.formal:
            message = f"Good day, {config.name}."
        else:
            message = f"Hello, {config.name}!"
        
        return GreetingResult(
            message=message,
            timestamp=context.now.isoformat(),
        )
```

### Step 3: Register in Module

```python
# my_module/module.py
from celine.dt.core.registry import DTRegistry
from .apps.greeting import GreetingApp

class MyModule:
    name = "my-module"
    version = "1.0.0"
    
    def register(self, registry: DTRegistry) -> None:
        registry.register_app(GreetingApp())

module = MyModule()
```

### Step 4: Configure

```yaml
# config/modules.yaml
modules:
  - name: my-module
    version: ">=1.0.0"
    import: celine.dt.modules.my_module.module:module
    enabled: true
```

### Step 5: Test

```python
# tests/test_greeting.py
import pytest
from celine.dt.core.registry import DTRegistry
from celine.dt.core.runner import DTAppRunner
from celine.dt.core.context import RunContext

from celine.dt.modules.my_module.apps.greeting import GreetingApp

@pytest.mark.asyncio
async def test_greeting_informal():
    registry = DTRegistry()
    registry.register_app(GreetingApp())
    
    runner = DTAppRunner()
    context = RunContext.create(datasets=None, state=None, token_provider=None)
    
    result = await runner.run(
        registry=registry,
        app_key="my-module.greeting",
        payload={"name": "World"},
        context=context,
    )
    
    assert result["message"] == "Hello, World!"
```

### Step 6: Use via API

```bash
# List apps
curl http://localhost:8000/apps

# Describe app
curl http://localhost:8000/apps/my-module.greeting/describe

# Run app
curl -X POST http://localhost:8000/apps/my-module.greeting/run \
  -H "Content-Type: application/json" \
  -d '{"name": "CELINE", "formal": true}'
```

---

## Part 2: Creating a Component

Components are pure, internal computation units.

### Step 1: Define Models

```python
# my_module/models.py
from pydantic import BaseModel

class EnergyBalanceInput(BaseModel):
    """Input for energy balance calculation."""
    generation_kwh: list[float]
    consumption_kwh: list[float]

class EnergyBalanceOutput(BaseModel):
    """Output from energy balance calculation."""
    self_consumption_ratio: float
    self_sufficiency_ratio: float
    grid_import_kwh: float
    grid_export_kwh: float
```

### Step 2: Implement the Component

Components implement the `DTComponent` protocol:

```python
# my_module/components/energy_balance.py
from celine.dt.contracts.component import DTComponent
from ..models import EnergyBalanceInput, EnergyBalanceOutput

class EnergyBalanceComponent(DTComponent[EnergyBalanceInput, EnergyBalanceOutput]):
    """Pure energy balance calculation."""
    
    key = "my-module.energy-balance"
    version = "1.0.0"
    
    input_type = EnergyBalanceInput
    output_type = EnergyBalanceOutput
    
    async def compute(
        self,
        input: EnergyBalanceInput,
        context,  # RunContext - available but optional for pure components
    ) -> EnergyBalanceOutput:
        # Pure computation - no side effects
        total_gen = sum(input.generation_kwh)
        total_cons = sum(input.consumption_kwh)
        
        # Simple model: self-consumed = min(gen, cons) at each timestep
        self_consumed = sum(
            min(g, c) for g, c in zip(input.generation_kwh, input.consumption_kwh)
        )
        
        grid_import = total_cons - self_consumed
        grid_export = total_gen - self_consumed
        
        return EnergyBalanceOutput(
            self_consumption_ratio=self_consumed / total_gen if total_gen > 0 else 0,
            self_sufficiency_ratio=self_consumed / total_cons if total_cons > 0 else 0,
            grid_import_kwh=grid_import,
            grid_export_kwh=grid_export,
        )
```

### Step 3: Register in Module

```python
# my_module/module.py
from celine.dt.core.registry import DTRegistry
from .apps.greeting import GreetingApp
from .components.energy_balance import EnergyBalanceComponent

class MyModule:
    name = "my-module"
    version = "1.0.0"
    
    def register(self, registry: DTRegistry) -> None:
        registry.register_app(GreetingApp())
        registry.register_component(EnergyBalanceComponent())

module = MyModule()
```

### Step 4: Use in Apps or Simulations

```python
# Inside an app or simulation
component = context.get_component("my-module.energy-balance")
result = await component.compute(
    EnergyBalanceInput(generation_kwh=[...], consumption_kwh=[...]),
    context,
)
```

---

## Part 3: Creating a Simulation

Simulations enable what-if exploration with a two-phase execution model.

### Step 1: Define Models

Four models are required:

```python
# my_module/models.py
from datetime import datetime
from pydantic import BaseModel, Field

# 1. Scenario Configuration - what context to build
class RECScenarioConfig(BaseModel):
    """Configuration for building a REC planning scenario."""
    community_id: str = Field(..., description="REC identifier")
    reference_start: datetime
    reference_end: datetime
    resolution: str = Field(default="1h")

# 2. Scenario - the built, immutable context
class RECScenario(BaseModel):
    """Built scenario with cached data and baseline metrics."""
    scenario_id: str = ""
    community_id: str
    reference_start: datetime
    reference_end: datetime
    baseline_consumption_kwh: float
    baseline_generation_kwh: float
    baseline_self_consumption_ratio: float

# 3. Parameters - what-if variables
class RECParameters(BaseModel):
    """Parameters for what-if exploration."""
    pv_kwp: float = Field(default=0.0, ge=0.0, description="Additional PV capacity")
    battery_kwh: float = Field(default=0.0, ge=0.0, description="Battery capacity")
    electricity_price: float = Field(default=0.25, ge=0.0)

# 4. Result - simulation output
class RECResult(BaseModel):
    """Result of a REC planning simulation."""
    self_consumption_ratio: float
    self_sufficiency_ratio: float
    npv_eur: float
    payback_years: float | None
```

### Step 2: Implement the Simulation

Simulations implement the `DTSimulation` protocol:

```python
# my_module/simulations/rec_planning.py
from celine.dt.contracts.simulation import DTSimulation
from ..models import RECScenarioConfig, RECScenario, RECParameters, RECResult

class RECPlanningSimulation(DTSimulation[RECScenarioConfig, RECScenario, RECParameters, RECResult]):
    """REC planning what-if simulation."""
    
    key = "my-module.rec-planning"
    version = "1.0.0"
    
    scenario_config_type = RECScenarioConfig
    scenario_type = RECScenario
    parameters_type = RECParameters
    result_type = RECResult
    
    async def build_scenario(
        self,
        config: RECScenarioConfig,
        workspace,  # FileWorkspace for storing artifacts
        context,    # RunContext for data fetching
    ) -> RECScenario:
        """
        Build scenario: EXPENSIVE operation.
        
        - Fetch historical data
        - Compute baseline metrics
        - Store intermediate artifacts
        """
        # Fetch consumption data via values
        consumption_data = await context.values.fetch(
            "consumption_timeseries",
            {
                "community_id": config.community_id,
                "start": config.reference_start.isoformat(),
                "end": config.reference_end.isoformat(),
            }
        )
        
        # Fetch generation data
        generation_data = await context.values.fetch(
            "generation_timeseries",
            {"community_id": config.community_id, ...}
        )
        
        # Compute baseline metrics
        total_consumption = sum(r["kwh"] for r in consumption_data)
        total_generation = sum(r["kwh"] for r in generation_data)
        self_consumed = min(total_consumption, total_generation)
        
        # Store artifacts in workspace (for later runs)
        await workspace.write_json("consumption.json", consumption_data)
        await workspace.write_json("generation.json", generation_data)
        
        return RECScenario(
            community_id=config.community_id,
            reference_start=config.reference_start,
            reference_end=config.reference_end,
            baseline_consumption_kwh=total_consumption,
            baseline_generation_kwh=total_generation,
            baseline_self_consumption_ratio=self_consumed / total_generation if total_generation > 0 else 0,
        )
    
    async def simulate(
        self,
        scenario: RECScenario,
        parameters: RECParameters,
        context,
    ) -> RECResult:
        """
        Run simulation: FAST operation.
        
        - Load cached scenario data
        - Apply parameters
        - Compute results
        """
        # Apply PV addition
        added_generation = parameters.pv_kwp * 1000  # Simplified
        total_generation = scenario.baseline_generation_kwh + added_generation
        
        # Compute new ratios
        self_consumed = min(scenario.baseline_consumption_kwh, total_generation)
        self_consumption_ratio = self_consumed / total_generation if total_generation > 0 else 0
        self_sufficiency_ratio = self_consumed / scenario.baseline_consumption_kwh
        
        # Simple economics
        investment = parameters.pv_kwp * 1200 + parameters.battery_kwh * 500
        annual_savings = (self_consumed - scenario.baseline_self_consumption_ratio * scenario.baseline_generation_kwh) * parameters.electricity_price
        
        npv = annual_savings * 20 - investment  # Simplified 20-year NPV
        payback = investment / annual_savings if annual_savings > 0 else None
        
        return RECResult(
            self_consumption_ratio=self_consumption_ratio,
            self_sufficiency_ratio=self_sufficiency_ratio,
            npv_eur=npv,
            payback_years=payback,
        )
    
    def get_default_parameters(self) -> RECParameters:
        """Return default parameters for baseline comparison."""
        return RECParameters()
```

### Step 3: Register in Module

```python
# my_module/module.py
from celine.dt.core.registry import DTRegistry
from .simulations.rec_planning import RECPlanningSimulation

class MyModule:
    name = "my-module"
    version = "1.0.0"
    
    def register(self, registry: DTRegistry) -> None:
        registry.register_simulation(RECPlanningSimulation())

module = MyModule()
```

### Step 4: Use via API

```bash
# 1. Build scenario (expensive, cached)
curl -X POST http://localhost:8000/simulations/my-module.rec-planning/scenarios \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "community_id": "rec-folgaria",
      "reference_start": "2024-01-01T00:00:00Z",
      "reference_end": "2024-12-31T23:59:59Z"
    },
    "ttl_hours": 24
  }'
# Returns: {"scenario_id": "abc123", ...}

# 2. Run simulation (fast, parameterized)
curl -X POST http://localhost:8000/simulations/my-module.rec-planning/runs \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "abc123",
    "parameters": {"pv_kwp": 100, "battery_kwh": 50}
  }'

# 3. Run parameter sweep
curl -X POST http://localhost:8000/simulations/my-module.rec-planning/sweep \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "abc123",
    "parameter_sets": [
      {"pv_kwp": 50},
      {"pv_kwp": 100},
      {"pv_kwp": 150}
    ],
    "include_baseline": true
  }'
```

---

## Part 4: Using Data in Apps and Simulations

### Option 1: Value Fetchers (Recommended)

Configure declarative fetchers:

```yaml
# config/values.yaml
values:
  consumption_timeseries:
    client: dataset_api
    query: |
      SELECT timestamp, kwh FROM consumption
      WHERE community_id = :community_id
        AND timestamp >= :start
        AND timestamp < :end
    payload:
      type: object
      required: [community_id, start, end]
      properties:
        community_id: { type: string }
        start: { type: string }
        end: { type: string }
```

Use in code:

```python
data = await context.values.fetch(
    "consumption_timeseries",
    {"community_id": "rec-folgaria", "start": "2024-01-01", "end": "2024-12-31"}
)
```

### Option 2: Direct Client Access

For complex queries:

```python
client = context.datasets
rows = await client.query(
    sql="SELECT * FROM consumption WHERE ...",
    limit=1000,
)
```

---

## Part 5: Publishing Events

Apps can publish events to brokers:

```python
from celine.dt.contracts.events import create_custom_event

class MyApp(DTApp[...]):
    async def run(self, config, context):
        # Compute result
        result = await self._compute(config)
        
        # Publish event
        if context.has_broker():
            event = create_custom_event(
                event_type="my-module.result-computed",
                payload={"value": result.value},
                source_app_key=self.key,
            )
            await context.publish_event(event)
        
        return result
```

---

## Part 6: Testing

### Unit Testing Apps

```python
@pytest.mark.asyncio
async def test_my_app():
    registry = DTRegistry()
    registry.register_app(MyApp())
    
    runner = DTAppRunner()
    context = RunContext.create(datasets=None, state=None, token_provider=None)
    
    result = await runner.run(
        registry=registry,
        app_key="my-module.my-app",
        payload={"input": "value"},
        context=context,
    )
    
    assert result["output"] == "expected"
```

### Unit Testing Components

```python
@pytest.mark.asyncio
async def test_energy_balance():
    component = EnergyBalanceComponent()
    
    result = await component.compute(
        EnergyBalanceInput(
            generation_kwh=[100, 200, 150],
            consumption_kwh=[80, 250, 100],
        ),
        context=None,  # Not needed for pure components
    )
    
    assert result.self_sufficiency_ratio > 0
```

### Unit Testing Simulations

```python
@pytest.mark.asyncio
async def test_rec_planning_simulation(tmp_path):
    from celine.dt.core.simulation.workspace import FileWorkspace
    
    simulation = RECPlanningSimulation()
    workspace = FileWorkspace("test", tmp_path)
    mock_context = MagicMock()
    
    # Test build_scenario
    config = RECScenarioConfig(
        community_id="test",
        reference_start=datetime(2024, 1, 1),
        reference_end=datetime(2024, 12, 31),
    )
    scenario = await simulation.build_scenario(config, workspace, mock_context)
    
    # Test simulate
    parameters = RECParameters(pv_kwp=100)
    result = await simulation.simulate(scenario, parameters, mock_context)
    
    assert result.self_consumption_ratio >= 0
```

---

## Common Patterns

### Using Components in Apps

```python
class MyApp(DTApp[...]):
    async def run(self, config, context):
        # Get component from registry
        energy_balance = context.get_component("energy-balance")
        
        # Use component
        balance = await energy_balance.compute(
            EnergyBalanceInput(...),
            context,
        )
        
        return MyResult(ratio=balance.self_consumption_ratio)
```

### Workspace Artifacts in Simulations

```python
async def build_scenario(self, config, workspace, context):
    # Store time series as Parquet
    await workspace.write_parquet("consumption.parquet", df)
    
    # Store metadata as JSON
    await workspace.write_json("metadata.json", {"version": "1.0"})
    
    # List artifacts
    files = await workspace.list_files()

async def simulate(self, scenario, parameters, context):
    # Read from workspace (attached to context)
    df = await context.workspace.read_parquet("consumption.parquet")
```

### Error Handling

```python
class MyApp(DTApp[...]):
    async def run(self, config, context):
        try:
            data = await context.values.fetch("my-data", {...})
        except ValueError as e:
            # Validation errors become 400 responses
            raise ValueError(f"Invalid input: {e}")
        except RuntimeError as e:
            # Runtime errors become 500 responses
            raise RuntimeError(f"Computation failed: {e}")
```

---

## Anti-Patterns to Avoid

❌ **Don't import infrastructure in domain code**
```python
# BAD
from fastapi import Request
from sqlalchemy import create_engine
```

❌ **Don't hardcode data access**
```python
# BAD
import requests
data = requests.get("https://api.example.com/data")
```

❌ **Don't use global state**
```python
# BAD
_cache = {}  # Module-level state
```

❌ **Don't test only via HTTP**
```python
# BAD - integration test as only test
def test_app():
    response = client.post("/apps/my-app/run", json={...})
```

✅ **Do use context for everything**
```python
# GOOD
data = await context.values.fetch("my-data", params)
await context.publish_event(event)
```

---

## Next Steps

- [Simulations](simulations.md) - Deep dive into simulation features
- [Values API](values.md) - Configure data fetchers
- [Brokers](brokers.md) - Set up event publishing
