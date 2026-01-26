# celine/dt/contracts/simulation.py
"""
DTSimulation contract for what-if exploration.

Simulations enable exploring scenarios with varying parameters:
1. Build a scenario (expensive: data fetching, baseline computation)
2. Run simulations with different parameters (fast: apply params to cached scenario)

This two-phase approach enables efficient parameter sweeps and sensitivity analysis.

Key characteristics:
- Scenario/Parameters separation: expensive setup vs cheap variations
- Workspace: temporary storage for scenario artifacts
- Caching: scenarios can be persisted and reused
- Composable: simulations use components for core logic
"""
from __future__ import annotations

from typing import Any, ClassVar, Generic, Protocol, Type, TypeVar, runtime_checkable

from pydantic import BaseModel


# Type variables for simulation generics
SC = TypeVar("SC", bound=BaseModel)  # Scenario Config
S = TypeVar("S", bound=BaseModel)  # Scenario (built from config)
P = TypeVar("P", bound=BaseModel)  # Parameters
R = TypeVar("R", bound=BaseModel)  # Result


@runtime_checkable
class DTSimulation(Protocol[SC, S, P, R]):
    """
    Digital Twin Simulation contract.

    A simulation explores what-if scenarios by:
    1. Building an immutable scenario from configuration (expensive)
    2. Running simulations with varying parameters (fast)

    Type Parameters:
        SC: Scenario configuration type (what context to build)
        S: Scenario type (the built, immutable context)
        P: Parameters type (what-if variables)
        R: Result type (simulation output)

    Attributes:
        key: Unique identifier in format "module.simulation-name"
        version: Semantic version string
        scenario_config_type: Pydantic model for scenario configuration
        scenario_type: Pydantic model for built scenario
        parameters_type: Pydantic model for simulation parameters
        result_type: Pydantic model for simulation results

    Example:
        class RECScenarioConfig(BaseModel):
            community_id: str
            reference_period: tuple[datetime, datetime]
            resolution: str = "1h"

        class RECScenario(BaseModel):
            workspace_id: str
            existing_pv_kwp: float
            baseline_self_consumption: float
            # ... cached data references

        class RECParameters(BaseModel):
            add_pv_kwp: float = 0.0
            add_battery_kwh: float = 0.0

        class RECResult(BaseModel):
            self_consumption_ratio: float
            self_sufficiency_ratio: float
            npv: float
            payback_years: float

        class RECPlanningSimulation(DTSimulation[RECScenarioConfig, RECScenario, RECParameters, RECResult]):
            key = "rec-planning"
            version = "1.0.0"

            scenario_config_type = RECScenarioConfig
            scenario_type = RECScenario
            parameters_type = RECParameters
            result_type = RECResult

            async def build_scenario(self, config, workspace, context) -> RECScenario:
                # Fetch data, compute baseline, store in workspace
                ...

            async def simulate(self, scenario, parameters, context) -> RECResult:
                # Apply parameters to scenario, compute results
                ...
    """

    key: ClassVar[str]
    version: ClassVar[str]

    scenario_config_type: Type[SC]
    scenario_type: Type[S]
    parameters_type: Type[P]
    result_type: Type[R]

    async def build_scenario(
        self,
        config: SC,
        workspace: Any,  # Workspace protocol
        context: Any,  # RunContext
    ) -> S:
        """
        Build an immutable scenario from configuration.

        This method performs expensive operations:
        - Fetch historical data via context.values
        - Compute baseline metrics
        - Store intermediate artifacts in workspace

        The resulting scenario is immutable and can be cached for
        multiple simulation runs with different parameters.

        Args:
            config: Scenario configuration specifying what context to build
            workspace: Workspace for storing artifacts (parquet, JSON, etc.)
            context: RunContext for data fetching and component access

        Returns:
            Built scenario object containing references to cached data

        Raises:
            ValueError: If configuration is invalid
            RuntimeError: If data fetching or computation fails
        """
        ...

    async def simulate(
        self,
        scenario: S,
        parameters: P,
        context: Any,  # RunContext
    ) -> R:
        """
        Run simulation with given parameters against a scenario.

        This method should be fast since the scenario is already built:
        - Load cached data from workspace
        - Apply parameters (e.g., add PV capacity)
        - Compute results using components
        - Return result metrics

        Args:
            scenario: Pre-built scenario (from build_scenario)
            parameters: What-if parameters to apply
            context: RunContext for component access

        Returns:
            Simulation result with computed metrics

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If simulation fails
        """
        ...

    def get_default_parameters(self) -> P:
        """
        Get default parameter values.

        Override to provide sensible defaults for parameter exploration.

        Returns:
            Parameters instance with default values
        """
        ...


class SimulationDescriptor:
    """
    Descriptor wrapping a simulation with metadata.

    Used by the registry to store and retrieve simulations.
    """

    def __init__(self, simulation: DTSimulation) -> None:
        self.simulation = simulation

    @property
    def key(self) -> str:
        return self.simulation.key

    @property
    def version(self) -> str:
        return self.simulation.version

    @property
    def scenario_config_schema(self) -> dict[str, Any]:
        """JSON Schema for scenario configuration."""
        return self.simulation.scenario_config_type.model_json_schema()

    @property
    def scenario_schema(self) -> dict[str, Any]:
        """JSON Schema for built scenario."""
        return self.simulation.scenario_type.model_json_schema()

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """JSON Schema for simulation parameters."""
        return self.simulation.parameters_type.model_json_schema()

    @property
    def result_schema(self) -> dict[str, Any]:
        """JSON Schema for simulation results."""
        return self.simulation.result_type.model_json_schema()

    def describe(self) -> dict[str, Any]:
        """Return simulation metadata for API responses."""
        return {
            "key": self.key,
            "version": self.version,
            "scenario_config_schema": self.scenario_config_schema,
            "parameters_schema": self.parameters_schema,
            "result_schema": self.result_schema,
        }


# Convenience type for parameter sweep results
class SweepResultItem(BaseModel):
    """Single result in a parameter sweep."""

    parameters: dict[str, Any]
    result: dict[str, Any]
    delta: dict[str, Any] | None = None  # Difference from baseline


class SweepResult(BaseModel):
    """Result of a parameter sweep (multiple simulations)."""

    scenario_id: str
    baseline: dict[str, Any] | None = None
    results: list[SweepResultItem]
    total_runs: int
    successful_runs: int
    failed_runs: int
