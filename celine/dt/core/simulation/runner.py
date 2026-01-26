# celine/dt/core/simulation/runner.py
"""
Simulation runner for executing simulations.

Handles the two-phase simulation process:
1. Build scenario (expensive, cacheable)
2. Run simulation (fast, parameterized)

Also supports parameter sweeps for batch execution.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from pydantic import BaseModel

from celine.dt.contracts.scenario import ScenarioMetadata, ScenarioRef
from celine.dt.contracts.simulation import DTSimulation, SweepResult, SweepResultItem
from celine.dt.core.simulation.registry import SimulationRegistry
from celine.dt.core.simulation.scenario import ScenarioService, compute_config_hash

logger = logging.getLogger(__name__)


class SimulationRunner:
    """
    Runner for executing Digital Twin simulations.

    Coordinates simulation execution including:
    - Scenario building and caching
    - Single-run simulation execution
    - Parameter sweep execution
    - Result comparison with baseline
    """

    def __init__(
        self,
        registry: SimulationRegistry,
        scenario_service: ScenarioService,
    ) -> None:
        """
        Initialize simulation runner.

        Args:
            registry: Registry of available simulations
            scenario_service: Service for scenario management
        """
        self._registry = registry
        self._scenario_service = scenario_service

    async def build_scenario(
        self,
        simulation_key: str,
        config: Mapping[str, Any],
        context: Any,
        ttl_hours: int | None = None,
        reuse_existing: bool = True,
    ) -> ScenarioRef:
        """
        Build a scenario for a simulation.

        This is the expensive phase that fetches data and computes baselines.
        Results are cached for reuse with different parameters.

        Args:
            simulation_key: Key of the simulation
            config: Scenario configuration
            context: RunContext for data fetching
            ttl_hours: Time-to-live for cached scenario
            reuse_existing: If True, reuse existing scenario with same config

        Returns:
            Reference to the built scenario

        Raises:
            KeyError: If simulation not found
            ValueError: If configuration is invalid
        """
        simulation = self._registry.get(simulation_key)

        # Convert config to dict if needed
        config_dict = dict(config)

        # Check for existing scenario with same config
        if reuse_existing:
            config_hash = compute_config_hash(config_dict)
            existing = await self._scenario_service.find_by_config_hash(
                simulation_key, config_hash
            )
            if existing:
                logger.info(
                    "Reusing existing scenario %s for simulation %s",
                    existing.scenario_id,
                    simulation_key,
                )
                return existing

        # Validate and parse config
        try:
            validated_config = simulation.scenario_config_type(**config_dict)
        except Exception as exc:
            raise ValueError(f"Invalid scenario configuration: {exc}") from exc

        # Create workspace for scenario artifacts
        workspace = self._scenario_service.create_workspace(simulation_key)

        try:
            # Build scenario
            logger.info(
                "Building scenario for simulation %s (workspace: %s)",
                simulation_key,
                workspace.id,
            )

            scenario = await simulation.build_scenario(
                config=validated_config,
                workspace=workspace,
                context=context,
            )

            # Compute baseline metrics if scenario has them
            baseline_metrics = {}
            if hasattr(scenario, "baseline_metrics"):
                baseline_metrics = scenario.baseline_metrics
            elif hasattr(scenario, "model_dump"):
                # Extract numeric fields as potential baseline metrics
                scenario_dict = scenario.model_dump()
                baseline_metrics = {
                    k: v
                    for k, v in scenario_dict.items()
                    if isinstance(v, (int, float)) and not k.startswith("_")
                }

            # Store scenario
            ref = await self._scenario_service.create_scenario(
                simulation_key=simulation_key,
                config=config_dict,
                scenario_data=scenario,
                workspace=workspace,
                baseline_metrics=baseline_metrics,
                ttl_hours=ttl_hours,
            )

            logger.info(
                "Built scenario %s for simulation %s",
                ref.scenario_id,
                simulation_key,
            )

            return ref

        except Exception as exc:
            # Clean up workspace on failure
            logger.error("Failed to build scenario: %s", exc)
            await workspace.cleanup()
            raise

    async def run(
        self,
        simulation_key: str,
        scenario_id: str,
        parameters: Mapping[str, Any],
        context: Any,
    ) -> dict[str, Any]:
        """
        Run a simulation with given parameters.

        Args:
            simulation_key: Key of the simulation
            scenario_id: ID of the pre-built scenario
            parameters: Simulation parameters
            context: RunContext for component access

        Returns:
            Simulation result as dictionary

        Raises:
            KeyError: If simulation or scenario not found
            ValueError: If parameters are invalid
        """
        simulation = self._registry.get(simulation_key)

        # Retrieve scenario
        scenario_data = await self._scenario_service.get_scenario(scenario_id)
        if scenario_data is None:
            raise KeyError(f"Scenario '{scenario_id}' not found or expired")

        metadata, scenario = scenario_data

        # Validate simulation key matches
        if metadata.simulation_key != simulation_key:
            raise ValueError(
                f"Scenario '{scenario_id}' belongs to simulation "
                f"'{metadata.simulation_key}', not '{simulation_key}'"
            )

        # Validate and parse parameters
        params_dict = dict(parameters)
        try:
            validated_params = simulation.parameters_type(**params_dict)
        except Exception as exc:
            raise ValueError(f"Invalid parameters: {exc}") from exc

        # Get workspace for scenario
        workspace = await self._scenario_service.get_workspace(scenario_id)

        # Inject workspace into context if needed
        # The context should have a method to access workspace
        if hasattr(context, "_set_workspace"):
            context._set_workspace(workspace)

        # Run simulation
        logger.debug(
            "Running simulation %s with scenario %s",
            simulation_key,
            scenario_id,
        )

        result = await simulation.simulate(
            scenario=scenario,
            parameters=validated_params,
            context=context,
        )

        # Convert result to dict
        if hasattr(result, "model_dump"):
            result_dict = result.model_dump()
        else:
            result_dict = dict(result)

        # Add baseline comparison if available
        if metadata.baseline_metrics:
            result_dict["_baseline"] = metadata.baseline_metrics
            result_dict["_delta"] = self._compute_delta(
                baseline=metadata.baseline_metrics,
                result=result_dict,
            )

        return result_dict

    async def run_with_inline_scenario(
        self,
        simulation_key: str,
        scenario_config: Mapping[str, Any],
        parameters: Mapping[str, Any],
        context: Any,
        ttl_hours: int = 1,
    ) -> dict[str, Any]:
        """
        Build scenario and run simulation in one call.

        Convenience method that builds a temporary scenario, runs the
        simulation, and returns the result. The scenario is cached
        briefly for potential follow-up runs.

        Args:
            simulation_key: Key of the simulation
            scenario_config: Scenario configuration
            parameters: Simulation parameters
            context: RunContext
            ttl_hours: Short TTL for temporary scenario

        Returns:
            Simulation result as dictionary
        """
        # Build scenario
        ref = await self.build_scenario(
            simulation_key=simulation_key,
            config=scenario_config,
            context=context,
            ttl_hours=ttl_hours,
            reuse_existing=True,
        )

        # Run simulation
        return await self.run(
            simulation_key=simulation_key,
            scenario_id=ref.scenario_id,
            parameters=parameters,
            context=context,
        )

    async def sweep(
        self,
        simulation_key: str,
        scenario_id: str,
        parameter_sets: list[Mapping[str, Any]],
        context: Any,
        include_baseline: bool = True,
    ) -> SweepResult:
        """
        Run multiple simulations with different parameters.

        Efficient for sensitivity analysis and parameter exploration.

        Args:
            simulation_key: Key of the simulation
            scenario_id: ID of the pre-built scenario
            parameter_sets: List of parameter dictionaries
            context: RunContext
            include_baseline: Include baseline run with default parameters

        Returns:
            SweepResult with all results and comparison
        """
        simulation = self._registry.get(simulation_key)

        # Get baseline
        baseline_dict = None
        if include_baseline:
            try:
                default_params = simulation.get_default_parameters()
                baseline_result = await self.run(
                    simulation_key=simulation_key,
                    scenario_id=scenario_id,
                    parameters=(
                        default_params.model_dump()
                        if hasattr(default_params, "model_dump")
                        else {}
                    ),
                    context=context,
                )
                baseline_dict = baseline_result
            except Exception as exc:
                logger.warning("Failed to compute baseline: %s", exc)

        # Run all parameter sets
        results: list[SweepResultItem] = []
        successful = 0
        failed = 0

        for params in parameter_sets:
            try:
                result = await self.run(
                    simulation_key=simulation_key,
                    scenario_id=scenario_id,
                    parameters=params,
                    context=context,
                )

                # Compute delta from baseline
                delta = None
                if baseline_dict:
                    delta = self._compute_delta(baseline_dict, result)

                results.append(
                    SweepResultItem(
                        parameters=dict(params),
                        result=result,
                        delta=delta,
                    )
                )
                successful += 1

            except Exception as exc:
                logger.error("Sweep run failed for params %s: %s", params, exc)
                results.append(
                    SweepResultItem(
                        parameters=dict(params),
                        result={"error": str(exc)},
                        delta=None,
                    )
                )
                failed += 1

        return SweepResult(
            scenario_id=scenario_id,
            baseline=baseline_dict,
            results=results,
            total_runs=len(parameter_sets),
            successful_runs=successful,
            failed_runs=failed,
        )

    def _compute_delta(
        self,
        baseline: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Compute difference between baseline and result.

        Only compares numeric fields.
        """
        delta = {}

        for key, baseline_value in baseline.items():
            if key.startswith("_"):
                continue

            result_value = result.get(key)

            if isinstance(baseline_value, (int, float)) and isinstance(
                result_value, (int, float)
            ):
                delta[key] = result_value - baseline_value

                # Also compute percentage change if baseline is non-zero
                if baseline_value != 0:
                    delta[f"{key}_pct"] = (
                        (result_value - baseline_value) / baseline_value * 100
                    )

        return delta
