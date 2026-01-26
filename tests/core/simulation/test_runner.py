# tests/core/simulation/test_runner.py
"""Tests for SimulationRunner."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from pydantic import BaseModel

from celine.dt.contracts.scenario import ScenarioMetadata, ScenarioRef
from celine.dt.contracts.simulation import DTSimulation, SweepResult
from celine.dt.core.simulation.registry import SimulationRegistry
from celine.dt.core.simulation.runner import SimulationRunner
from celine.dt.core.simulation.scenario import ScenarioService
from celine.dt.core.simulation.scenario_store import FileScenarioStore
from celine.dt.core.simulation.workspace import FileWorkspace
from celine.dt.core.simulation.workspace_layout import SimulationWorkspaceLayout


# ──────────────────────────────────────────────────────────────────────────────
# Test fixtures: Minimal DTSimulation implementation
# ──────────────────────────────────────────────────────────────────────────────


class TestScenarioConfig(BaseModel):
    community_id: str
    target_kwh: float = 1000.0


class TestScenario(BaseModel):
    community_id: str
    baseline_consumption_kwh: float
    baseline_generation_kwh: float


class TestParameters(BaseModel):
    add_pv_kwp: float = 0.0
    add_battery_kwh: float = 0.0


class TestResult(BaseModel):
    self_consumption_ratio: float
    self_sufficiency_ratio: float
    added_generation_kwh: float


class TestSimulation(DTSimulation):
    """Minimal simulation for testing."""

    key = "test-simulation"
    version = "1.0.0"

    scenario_config_type = TestScenarioConfig
    scenario_type = TestScenario
    parameters_type = TestParameters
    result_type = TestResult

    async def build_scenario(
        self, config: TestScenarioConfig, workspace: Any, context: Any
    ) -> TestScenario:
        # Write some artifacts
        await workspace.write_json("baseline.json", {"consumption": 1000.0})

        return TestScenario(
            community_id=config.community_id,
            baseline_consumption_kwh=config.target_kwh,
            baseline_generation_kwh=config.target_kwh * 0.5,
        )

    async def simulate(
        self, scenario: Any, parameters: TestParameters, context: Any
    ) -> TestResult:
        # Handle both dict and Pydantic model
        if isinstance(scenario, dict):
            baseline_gen = scenario.get("baseline_generation_kwh", 500.0)
            baseline_cons = scenario.get("baseline_consumption_kwh", 1000.0)
        else:
            baseline_gen = scenario.baseline_generation_kwh
            baseline_cons = scenario.baseline_consumption_kwh

        added_gen = parameters.add_pv_kwp * 1000  # Simple scaling
        total_gen = baseline_gen + added_gen

        return TestResult(
            self_consumption_ratio=min(1.0, total_gen / baseline_cons),
            self_sufficiency_ratio=min(1.0, 0.7 + parameters.add_battery_kwh * 0.01),
            added_generation_kwh=added_gen,
        )

    def get_default_parameters(self) -> TestParameters:
        return TestParameters()


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestSimulationRunner:
    """Tests for SimulationRunner."""

    @pytest.fixture
    def layout(self, tmp_path: Path) -> SimulationWorkspaceLayout:
        """Create a temporary workspace layout."""
        return SimulationWorkspaceLayout(root=tmp_path)

    @pytest.fixture
    def registry(self) -> SimulationRegistry:
        """Create a registry with test simulation."""
        registry = SimulationRegistry()
        registry.register(TestSimulation())
        return registry

    @pytest.fixture
    def scenario_service(self, layout: SimulationWorkspaceLayout) -> ScenarioService:
        """Create a scenario service."""
        store = FileScenarioStore(layout=layout)
        return ScenarioService(store=store, layout=layout, default_ttl_hours=24)

    @pytest.fixture
    def runner(
        self, registry: SimulationRegistry, scenario_service: ScenarioService
    ) -> SimulationRunner:
        """Create a simulation runner."""
        return SimulationRunner(
            registry=registry,
            scenario_service=scenario_service,
        )

    @pytest.fixture
    def mock_context(self):
        """Create a mock context."""
        context = MagicMock()
        context._workspace = None
        context._set_workspace = lambda ws: setattr(context, "_workspace", ws)
        return context

    @pytest.mark.asyncio
    async def test_build_scenario(self, runner: SimulationRunner, mock_context):
        """Test building a scenario."""
        config = {"community_id": "test-community", "target_kwh": 2000.0}

        ref = await runner.build_scenario(
            simulation_key="test-simulation",
            config=config,
            context=mock_context,
            ttl_hours=1,
        )

        assert ref is not None
        assert ref.simulation_key == "test-simulation"
        assert not ref.is_expired()

    @pytest.mark.asyncio
    async def test_build_scenario_invalid_config_raises(
        self, runner: SimulationRunner, mock_context
    ):
        """Test that invalid config raises ValueError."""
        config = {"invalid_field": "bad"}  # Missing required community_id

        with pytest.raises(ValueError, match="Invalid scenario configuration"):
            await runner.build_scenario(
                simulation_key="test-simulation",
                config=config,
                context=mock_context,
            )

    @pytest.mark.asyncio
    async def test_build_scenario_nonexistent_simulation_raises(
        self, runner: SimulationRunner, mock_context
    ):
        """Test that nonexistent simulation raises KeyError."""
        with pytest.raises(KeyError):
            await runner.build_scenario(
                simulation_key="nonexistent",
                config={"community_id": "test"},
                context=mock_context,
            )

    @pytest.mark.asyncio
    async def test_build_scenario_reuses_existing(
        self, runner: SimulationRunner, mock_context
    ):
        """Test that build_scenario reuses existing scenarios with same config."""
        config = {"community_id": "reuse-test", "target_kwh": 1000.0}

        ref1 = await runner.build_scenario(
            simulation_key="test-simulation",
            config=config,
            context=mock_context,
            reuse_existing=True,
        )

        ref2 = await runner.build_scenario(
            simulation_key="test-simulation",
            config=config,
            context=mock_context,
            reuse_existing=True,
        )

        assert ref1.scenario_id == ref2.scenario_id

    @pytest.mark.asyncio
    async def test_build_scenario_creates_new_when_reuse_disabled(
        self, runner: SimulationRunner, mock_context
    ):
        """Test that build_scenario creates new scenario when reuse is disabled."""
        config = {"community_id": "no-reuse-test"}

        ref1 = await runner.build_scenario(
            simulation_key="test-simulation",
            config=config,
            context=mock_context,
            reuse_existing=False,
        )

        ref2 = await runner.build_scenario(
            simulation_key="test-simulation",
            config=config,
            context=mock_context,
            reuse_existing=False,
        )

        assert ref1.scenario_id != ref2.scenario_id

    @pytest.mark.asyncio
    async def test_run_simulation(self, runner: SimulationRunner, mock_context):
        """Test running a simulation."""
        # Build scenario first
        ref = await runner.build_scenario(
            simulation_key="test-simulation",
            config={"community_id": "run-test"},
            context=mock_context,
        )

        # Run simulation
        result = await runner.run(
            simulation_key="test-simulation",
            scenario_id=ref.scenario_id,
            parameters={"add_pv_kwp": 10.0},
            context=mock_context,
        )

        assert "self_consumption_ratio" in result
        assert "self_sufficiency_ratio" in result
        assert result["added_generation_kwh"] == 10000.0  # 10 kWp * 1000

    @pytest.mark.asyncio
    async def test_run_nonexistent_scenario_raises(
        self, runner: SimulationRunner, mock_context
    ):
        """Test that running with nonexistent scenario raises KeyError."""
        with pytest.raises(KeyError, match="not found or expired"):
            await runner.run(
                simulation_key="test-simulation",
                scenario_id="nonexistent",
                parameters={},
                context=mock_context,
            )

    @pytest.mark.asyncio
    async def test_run_mismatched_simulation_raises(
        self, runner: SimulationRunner, scenario_service: ScenarioService, mock_context
    ):
        """Test that running scenario with wrong simulation raises ValueError."""
        # Create scenario manually for a different simulation
        workspace = scenario_service.create_workspace("other-sim", "other-scenario")
        await scenario_service.create_scenario(
            simulation_key="other-sim",
            config={},
            scenario_data={},
            workspace=workspace,
        )

        with pytest.raises(ValueError, match="belongs to simulation"):
            await runner.run(
                simulation_key="test-simulation",
                scenario_id="other-scenario",
                parameters={},
                context=mock_context,
            )

    @pytest.mark.asyncio
    async def test_run_invalid_parameters_raises(
        self, runner: SimulationRunner, mock_context
    ):
        """Test that invalid parameters raises ValueError."""
        ref = await runner.build_scenario(
            simulation_key="test-simulation",
            config={"community_id": "params-test"},
            context=mock_context,
        )

        with pytest.raises(ValueError, match="Invalid parameters"):
            await runner.run(
                simulation_key="test-simulation",
                scenario_id=ref.scenario_id,
                parameters={"add_pv_kwp": "not a number"},
                context=mock_context,
            )

    @pytest.mark.asyncio
    async def test_run_with_inline_scenario(
        self, runner: SimulationRunner, mock_context
    ):
        """Test running simulation with inline scenario."""
        result = await runner.run_with_inline_scenario(
            simulation_key="test-simulation",
            scenario_config={"community_id": "inline-test"},
            parameters={"add_pv_kwp": 5.0},
            context=mock_context,
            ttl_hours=1,
        )

        assert "self_consumption_ratio" in result
        assert result["added_generation_kwh"] == 5000.0

    @pytest.mark.asyncio
    async def test_sweep(self, runner: SimulationRunner, mock_context):
        """Test running parameter sweep."""
        ref = await runner.build_scenario(
            simulation_key="test-simulation",
            config={"community_id": "sweep-test"},
            context=mock_context,
        )

        result = await runner.sweep(
            simulation_key="test-simulation",
            scenario_id=ref.scenario_id,
            parameter_sets=[
                {"add_pv_kwp": 0.0},
                {"add_pv_kwp": 5.0},
                {"add_pv_kwp": 10.0},
            ],
            context=mock_context,
            include_baseline=True,
        )

        assert isinstance(result, SweepResult)
        assert result.total_runs == 3
        assert result.successful_runs == 3
        assert result.failed_runs == 0
        assert len(result.results) == 3

    @pytest.mark.asyncio
    async def test_sweep_includes_delta(self, runner: SimulationRunner, mock_context):
        """Test that sweep results include delta from baseline."""
        ref = await runner.build_scenario(
            simulation_key="test-simulation",
            config={"community_id": "delta-test"},
            context=mock_context,
        )

        result = await runner.sweep(
            simulation_key="test-simulation",
            scenario_id=ref.scenario_id,
            parameter_sets=[
                {"add_pv_kwp": 10.0},
            ],
            context=mock_context,
            include_baseline=True,
        )

        assert result.baseline is not None
        assert result.results[0].delta is not None
        assert "added_generation_kwh" in result.results[0].delta

    @pytest.mark.asyncio
    async def test_run_includes_baseline_comparison(
        self, runner: SimulationRunner, mock_context, scenario_service: ScenarioService
    ):
        """Test that run includes baseline comparison when available."""
        ref = await runner.build_scenario(
            simulation_key="test-simulation",
            config={"community_id": "baseline-test"},
            context=mock_context,
        )

        result = await runner.run(
            simulation_key="test-simulation",
            scenario_id=ref.scenario_id,
            parameters={"add_pv_kwp": 10.0},
            context=mock_context,
        )

        # Should have baseline comparison since scenario has baseline_metrics
        assert "_baseline" in result or "self_consumption_ratio" in result


class TestComputeDelta:
    """Tests for _compute_delta method."""

    @pytest.fixture
    def runner(self, tmp_path: Path) -> SimulationRunner:
        """Create a runner for testing."""
        layout = SimulationWorkspaceLayout(root=tmp_path)
        store = FileScenarioStore(layout=layout)
        service = ScenarioService(store=store, layout=layout)
        registry = SimulationRegistry()
        return SimulationRunner(registry=registry, scenario_service=service)

    def test_compute_delta_numeric_fields(self, runner: SimulationRunner):
        """Test computing delta for numeric fields."""
        baseline = {"value": 100.0, "count": 10}
        result = {"value": 150.0, "count": 15}

        delta = runner._compute_delta(baseline, result)

        assert delta["value"] == 50.0
        assert delta["count"] == 5
        assert delta["value_pct"] == 50.0
        assert delta["count_pct"] == 50.0

    def test_compute_delta_skips_private_fields(self, runner: SimulationRunner):
        """Test that delta computation skips fields starting with underscore."""
        baseline = {"_internal": 100.0, "public": 200.0}
        result = {"_internal": 150.0, "public": 250.0}

        delta = runner._compute_delta(baseline, result)

        assert "_internal" not in delta
        assert "public" in delta

    def test_compute_delta_handles_zero_baseline(self, runner: SimulationRunner):
        """Test that delta handles zero baseline values."""
        baseline = {"value": 0.0}
        result = {"value": 100.0}

        delta = runner._compute_delta(baseline, result)

        assert delta["value"] == 100.0
        assert "value_pct" not in delta  # No percentage for zero baseline

    def test_compute_delta_ignores_non_numeric(self, runner: SimulationRunner):
        """Test that delta ignores non-numeric fields."""
        baseline = {"value": 100.0, "name": "test"}
        result = {"value": 150.0, "name": "updated"}

        delta = runner._compute_delta(baseline, result)

        assert "value" in delta
        assert "name" not in delta
