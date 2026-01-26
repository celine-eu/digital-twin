# Simulations

This document covers the **Simulation Engine** in depth—the two-phase execution model, workspace management, scenario caching, and parameter sweeps.

---

## Overview

Simulations enable **what-if exploration** by separating expensive setup from fast parameter variations:

| Phase | Operation | Cost | Caching |
|-------|-----------|------|---------|
| **Build Scenario** | Fetch data, compute baseline | Expensive (seconds–minutes) | Cached by config hash |
| **Run Simulation** | Apply parameters, compute results | Fast (milliseconds) | Not cached |

This design enables:
- Testing 100 parameter combinations against one scenario
- Sensitivity analysis without re-fetching data
- Scenario comparison across communities or time periods

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Simulation Subsystem                                 │
│                                                                              │
│  ┌──────────────────┐                                                       │
│  │ SimulationRunner │ ◄─── Orchestrates build + run                         │
│  └────────┬─────────┘                                                       │
│           │                                                                  │
│           ▼                                                                  │
│  ┌──────────────────┐     ┌─────────────────┐     ┌────────────────────┐   │
│  │ SimulationRegistry    │ ScenarioService │     │   FileWorkspace    │   │
│  │                  │     │                 │     │                    │   │
│  │ - Registered     │     │ - Create/Get    │     │ - Store artifacts  │   │
│  │   simulations    │     │ - List/Delete   │     │ - JSON/Parquet     │   │
│  │ - Descriptors    │     │ - Find by hash  │     │ - Lifecycle mgmt   │   │
│  └──────────────────┘     └─────────────────┘     └────────────────────┘   │
│                                   │                         │               │
│                                   ▼                         ▼               │
│                           ┌─────────────────┐     ┌────────────────────┐   │
│                           │ FileScenarioStore   │ SimWorkspaceLayout │   │
│                           │                 │     │                    │   │
│                           │ - Metadata JSON │     │ - Directory paths  │   │
│                           │ - Scenario JSON │     │ - scenarios/       │   │
│                           └─────────────────┘     │ - runs/            │   │
│                                                   └────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### List Simulations

```http
GET /simulations
```

Response:
```json
[
  {
    "key": "rec.rec-planning",
    "version": "1.0.0"
  }
]
```

### Describe Simulation

```http
GET /simulations/{key}/describe
```

Response:
```json
{
  "key": "rec.rec-planning",
  "version": "1.0.0",
  "scenario_config_schema": { ... },
  "parameters_schema": { ... },
  "result_schema": { ... }
}
```

### Build Scenario

```http
POST /simulations/{key}/scenarios
Content-Type: application/json

{
  "config": {
    "community_id": "rec-folgaria",
    "reference_start": "2024-01-01T00:00:00Z",
    "reference_end": "2024-12-31T23:59:59Z",
    "resolution": "1h"
  },
  "ttl_hours": 24,
  "reuse_existing": true
}
```

Response:
```json
{
  "scenario_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "simulation_key": "rec.rec-planning",
  "created_at": "2024-01-15T10:30:00Z",
  "expires_at": "2024-01-16T10:30:00Z",
  "config_hash": "abc123def456",
  "baseline_metrics": {
    "baseline_consumption_kwh": 50000.0,
    "baseline_generation_kwh": 12000.0,
    "baseline_self_consumption_ratio": 0.45
  }
}
```

### List Scenarios

```http
GET /simulations/{key}/scenarios?include_expired=false
```

### Get Scenario Details

```http
GET /simulations/{key}/scenarios/{scenario_id}
```

### Delete Scenario

```http
DELETE /simulations/{key}/scenarios/{scenario_id}
```

### Run Simulation

```http
POST /simulations/{key}/runs
Content-Type: application/json

{
  "scenario_id": "a1b2c3d4-...",
  "parameters": {
    "pv_kwp": 100.0,
    "battery_kwh": 50.0
  }
}
```

Response:
```json
{
  "self_consumption_ratio": 0.72,
  "self_sufficiency_ratio": 0.85,
  "npv_eur": 15000.0,
  "payback_years": 8.5,
  "_baseline": { ... },
  "_delta": {
    "self_consumption_ratio": 0.27,
    "self_consumption_ratio_pct": 60.0
  }
}
```

### Run Inline (Build + Run)

```http
POST /simulations/{key}/run-inline
Content-Type: application/json

{
  "scenario": {
    "community_id": "rec-folgaria",
    "reference_start": "2024-01-01T00:00:00Z",
    "reference_end": "2024-12-31T23:59:59Z"
  },
  "parameters": {
    "pv_kwp": 100.0
  },
  "ttl_hours": 1
}
```

### Parameter Sweep

```http
POST /simulations/{key}/sweep
Content-Type: application/json

{
  "scenario_id": "a1b2c3d4-...",
  "parameter_sets": [
    {"pv_kwp": 50},
    {"pv_kwp": 100},
    {"pv_kwp": 150},
    {"pv_kwp": 200}
  ],
  "include_baseline": true
}
```

Response:
```json
{
  "scenario_id": "a1b2c3d4-...",
  "baseline": {
    "self_consumption_ratio": 0.45,
    "npv_eur": 0
  },
  "results": [
    {
      "parameters": {"pv_kwp": 50},
      "result": {"self_consumption_ratio": 0.55, "npv_eur": 5000},
      "delta": {"self_consumption_ratio": 0.10, "npv_eur": 5000}
    },
    {
      "parameters": {"pv_kwp": 100},
      "result": {"self_consumption_ratio": 0.65, "npv_eur": 8000},
      "delta": {"self_consumption_ratio": 0.20, "npv_eur": 8000}
    }
  ],
  "total_runs": 4,
  "successful_runs": 4,
  "failed_runs": 0
}
```

---

## Scenario Caching

### How It Works

Scenarios are cached based on a **config hash**—a deterministic hash of the scenario configuration:

```python
# Same config → same hash → reuse scenario
config_hash = compute_config_hash({
    "community_id": "rec-folgaria",
    "reference_start": "2024-01-01T00:00:00Z",
    "reference_end": "2024-12-31T23:59:59Z",
})
# → "abc123def456"
```

When `reuse_existing: true` (default):
1. Compute config hash
2. Look for existing scenario with same hash
3. If found and not expired, return existing
4. Otherwise, build new scenario

### TTL and Expiration

Scenarios expire after `ttl_hours`:

```json
{
  "config": { ... },
  "ttl_hours": 24
}
```

Expired scenarios are:
- Excluded from reuse lookups
- Excluded from list results (unless `include_expired=true`)
- Cleaned up by background tasks

### Forcing Fresh Build

```json
{
  "config": { ... },
  "reuse_existing": false
}
```

---

## Workspace System

Each scenario gets a **workspace** for storing artifacts:

```
dt_workspaces/
└── simulations/
    └── rec.rec-planning/
        └── scenarios/
            └── a1b2c3d4-e5f6-7890-abcd-ef1234567890/
                ├── metadata.json      # Scenario metadata
                ├── scenario.json      # Scenario object
                ├── consumption.parquet # Time series artifact
                ├── generation.parquet  # Time series artifact
                └── baseline.json      # Computed baseline
```

### Workspace Operations

In `build_scenario`:

```python
async def build_scenario(self, config, workspace, context):
    # Write JSON
    await workspace.write_json("baseline.json", {"value": 123})
    
    # Write Parquet (for DataFrames)
    await workspace.write_parquet("consumption.parquet", df)
    
    # Write raw bytes
    await workspace.write_bytes("model.pkl", pickle.dumps(model))
    
    # List files
    files = await workspace.list_files()
    # → ["baseline.json", "consumption.parquet", "model.pkl"]
```

In `simulate`:

```python
async def simulate(self, scenario, parameters, context):
    # Workspace is attached to context
    baseline = await context.workspace.read_json("baseline.json")
    df = await context.workspace.read_parquet("consumption.parquet")
```

---

## Implementing a Simulation

### Required Type Definitions

```python
from pydantic import BaseModel

# 1. Scenario Configuration - defines WHAT data to fetch
class MyScenarioConfig(BaseModel):
    entity_id: str
    start_date: datetime
    end_date: datetime
    resolution: str = "1h"

# 2. Scenario - the cached, immutable context
class MyScenario(BaseModel):
    scenario_id: str = ""
    entity_id: str
    baseline_value: float
    # References to workspace artifacts
    artifacts: list[str] = []

# 3. Parameters - what-if variables
class MyParameters(BaseModel):
    factor_a: float = 1.0
    factor_b: float = 0.0

# 4. Result - simulation output
class MyResult(BaseModel):
    computed_value: float
    delta_from_baseline: float
```

### Simulation Implementation

```python
from celine.dt.contracts.simulation import DTSimulation

class MySimulation(DTSimulation[MyScenarioConfig, MyScenario, MyParameters, MyResult]):
    key = "my-module.my-simulation"
    version = "1.0.0"
    
    scenario_config_type = MyScenarioConfig
    scenario_type = MyScenario
    parameters_type = MyParameters
    result_type = MyResult
    
    async def build_scenario(
        self,
        config: MyScenarioConfig,
        workspace,  # FileWorkspace
        context,    # RunContext
    ) -> MyScenario:
        """
        EXPENSIVE: Fetch data, compute baseline, store artifacts.
        Called once, then cached.
        """
        # 1. Fetch data
        data = await context.values.fetch("my_data", {
            "entity_id": config.entity_id,
            "start": config.start_date.isoformat(),
            "end": config.end_date.isoformat(),
        })
        
        # 2. Compute baseline
        baseline = sum(row["value"] for row in data) / len(data)
        
        # 3. Store artifacts
        await workspace.write_json("data.json", data)
        await workspace.write_json("baseline.json", {"value": baseline})
        
        # 4. Return scenario
        return MyScenario(
            entity_id=config.entity_id,
            baseline_value=baseline,
            artifacts=await workspace.list_files(),
        )
    
    async def simulate(
        self,
        scenario: MyScenario,  # May be dict when loaded from storage
        parameters: MyParameters,
        context,
    ) -> MyResult:
        """
        FAST: Apply parameters to scenario, compute result.
        Called many times with different parameters.
        """
        # Handle both dict and Pydantic model
        if isinstance(scenario, dict):
            baseline = scenario["baseline_value"]
        else:
            baseline = scenario.baseline_value
        
        # Apply parameters
        computed = baseline * parameters.factor_a + parameters.factor_b
        
        return MyResult(
            computed_value=computed,
            delta_from_baseline=computed - baseline,
        )
    
    def get_default_parameters(self) -> MyParameters:
        """Return default parameters for baseline comparison."""
        return MyParameters()
```

---

## Best Practices

### Scenario Design

**Do:**
- Keep scenarios immutable after build
- Store intermediate artifacts for debugging
- Include baseline metrics in scenario
- Use deterministic computations

**Don't:**
- Store parameters in scenario
- Modify workspace during simulate
- Rely on external state during simulate

### Parameter Design

**Do:**
- Provide sensible defaults
- Use Field constraints (ge=0, le=100)
- Include units in descriptions
- Group related parameters

**Don't:**
- Include data fetch parameters (those go in scenario config)
- Make parameters that change scenario structure

### Performance

**Do:**
- Pre-compute expensive values in build_scenario
- Store time series as Parquet (compressed, columnar)
- Use numpy/pandas for vectorized operations
- Keep simulate < 100ms

**Don't:**
- Fetch data in simulate
- Re-parse artifacts repeatedly
- Use Python loops for large arrays

---

## Testing Simulations

### Unit Test Structure

```python
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from celine.dt.core.simulation.workspace import FileWorkspace
from my_module.simulations.my_simulation import MySimulation
from my_module.models import MyScenarioConfig, MyParameters

@pytest.fixture
def simulation():
    return MySimulation()

@pytest.fixture
def workspace(tmp_path):
    return FileWorkspace("test-scenario", tmp_path / "workspace")

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.values = AsyncMock()
    context.values.fetch.return_value = [
        {"value": 100},
        {"value": 200},
        {"value": 150},
    ]
    return context

@pytest.mark.asyncio
async def test_build_scenario(simulation, workspace, mock_context):
    config = MyScenarioConfig(
        entity_id="test-entity",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
    )
    
    scenario = await simulation.build_scenario(config, workspace, mock_context)
    
    assert scenario.entity_id == "test-entity"
    assert scenario.baseline_value == 150.0  # Average of mock data
    assert len(scenario.artifacts) > 0

@pytest.mark.asyncio
async def test_simulate(simulation, workspace, mock_context):
    # Build scenario first
    config = MyScenarioConfig(...)
    scenario = await simulation.build_scenario(config, workspace, mock_context)
    
    # Attach workspace to context
    mock_context.workspace = workspace
    
    # Test simulation
    parameters = MyParameters(factor_a=2.0)
    result = await simulation.simulate(scenario, parameters, mock_context)
    
    assert result.computed_value == 300.0  # 150 * 2.0
    assert result.delta_from_baseline == 150.0

@pytest.mark.asyncio
async def test_default_parameters(simulation):
    params = simulation.get_default_parameters()
    
    assert params.factor_a == 1.0
    assert params.factor_b == 0.0
```

---

## Configuration

### Environment Settings

```bash
# Workspace root directory
DT_WORKSPACE_ROOT=dt_workspaces

# Default scenario TTL
DT_SCENARIO_DEFAULT_TTL_HOURS=24
```

### Directory Structure

```
${DT_WORKSPACE_ROOT}/
└── simulations/
    └── {simulation_key}/
        ├── scenarios/
        │   └── {scenario_id}/
        │       ├── metadata.json
        │       ├── scenario.json
        │       └── ... artifacts ...
        └── runs/
            └── {run_id}/
                └── ... run artifacts ...
```

---

## Troubleshooting

### Scenario Not Found

```json
{"detail": "Scenario 'abc123' not found or expired"}
```

- Check scenario_id is correct
- Verify scenario hasn't expired
- Use `include_expired=true` to list all scenarios

### Simulation Key Mismatch

```json
{"detail": "Scenario belongs to simulation 'other-sim', not 'my-sim'"}
```

- Each scenario is bound to a specific simulation
- Use the correct simulation key

### Invalid Parameters

```json
{"detail": "Invalid parameters: factor_a must be >= 0"}
```

- Parameters are validated against Pydantic schema
- Check parameter constraints

### Workspace Errors

```json
{"detail": "File 'missing.json' not found in workspace"}
```

- Verify artifact was written during build_scenario
- Check workspace.list_files() for available artifacts
