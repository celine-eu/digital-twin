# tests/modules/rec_planning/test_simulation.py
"""Tests for REC Planning simulation."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from pydantic import BaseModel

from celine.dt.modules.rec_planning.models import (
    RECScenarioConfig,
    RECScenario,
    RECPlanningParameters,
    RECPlanningResult,
)
from celine.dt.modules.rec_planning.simulation import RECPlanningSimulation
from celine.dt.core.simulation.workspace import FileWorkspace


class TestRECPlanningSimulation:
    """Tests for RECPlanningSimulation."""

    @pytest.fixture
    def simulation(self) -> RECPlanningSimulation:
        """Create a simulation instance."""
        return RECPlanningSimulation()

    @pytest.fixture
    def workspace(self, tmp_path: Path) -> FileWorkspace:
        """Create a temporary workspace."""
        return FileWorkspace("test-workspace", tmp_path / "workspace")

    @pytest.fixture
    def mock_context(self):
        """Create a mock context."""
        return MagicMock()

    def test_simulation_metadata(self, simulation: RECPlanningSimulation):
        """Test simulation has correct metadata."""
        assert simulation.key == "rec.rec-planning"
        assert simulation.version == "0.1.0"

    def test_simulation_types(self, simulation: RECPlanningSimulation):
        """Test simulation has correct type definitions."""
        assert simulation.scenario_config_type == RECScenarioConfig
        assert simulation.scenario_type == RECScenario
        assert simulation.parameters_type == RECPlanningParameters
        assert simulation.result_type == RECPlanningResult

    @pytest.mark.asyncio
    async def test_build_scenario_basic(
        self,
        simulation: RECPlanningSimulation,
        workspace: FileWorkspace,
        mock_context,
    ):
        """Test building a basic scenario."""
        config = RECScenarioConfig(
            community_id="test-community",
            reference_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            reference_end=datetime(2024, 1, 8, tzinfo=timezone.utc),  # 1 week
            resolution="1h",
        )

        scenario = await simulation.build_scenario(config, workspace, mock_context)

        assert scenario.community_id == "test-community"
        assert scenario.baseline_total_consumption_kwh > 0
        assert scenario.baseline_total_generation_kwh >= 0
        assert 0.0 <= scenario.baseline_self_consumption_ratio <= 1.0
        assert 0.0 <= scenario.baseline_self_sufficiency_ratio <= 1.0

    @pytest.mark.asyncio
    async def test_build_scenario_with_existing_pv(
        self,
        simulation: RECPlanningSimulation,
        workspace: FileWorkspace,
        mock_context,
    ):
        """Test building scenario with existing PV capacity."""
        config = RECScenarioConfig(
            community_id="pv-community",
            reference_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            reference_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
            assumptions={"existing_pv_kwp": 100.0},
        )

        scenario = await simulation.build_scenario(config, workspace, mock_context)

        assert scenario.baseline_total_generation_kwh > 0

    @pytest.mark.asyncio
    async def test_build_scenario_invalid_dates_raises(
        self,
        simulation: RECPlanningSimulation,
        workspace: FileWorkspace,
        mock_context,
    ):
        """Test that invalid date range raises ValueError."""
        config = RECScenarioConfig(
            community_id="invalid-dates",
            reference_start=datetime(2024, 1, 8, tzinfo=timezone.utc),
            reference_end=datetime(2024, 1, 1, tzinfo=timezone.utc),  # End before start
        )

        with pytest.raises(ValueError, match="must be after"):
            await simulation.build_scenario(config, workspace, mock_context)

    @pytest.mark.asyncio
    async def test_build_scenario_writes_artifacts(
        self,
        simulation: RECPlanningSimulation,
        workspace: FileWorkspace,
        mock_context,
    ):
        """Test that scenario build writes artifacts to workspace."""
        config = RECScenarioConfig(
            community_id="artifacts-test",
            reference_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            reference_end=datetime(2024, 1, 2, tzinfo=timezone.utc),
        )

        scenario = await simulation.build_scenario(config, workspace, mock_context)

        # Should have created baseline artifacts (either parquet or JSON)
        files = await workspace.list_files()
        assert len(files) > 0
        assert any("baseline" in f for f in files)

    @pytest.mark.asyncio
    async def test_simulate_basic(
        self,
        simulation: RECPlanningSimulation,
        workspace: FileWorkspace,
        mock_context,
    ):
        """Test running a basic simulation."""
        # Build scenario first
        config = RECScenarioConfig(
            community_id="sim-test",
            reference_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            reference_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
        )
        scenario = await simulation.build_scenario(config, workspace, mock_context)

        # Run simulation with parameters
        parameters = RECPlanningParameters(
            pv_kwp=50.0,
            battery_kwh=20.0,
        )

        # Attach workspace to context for the simulation
        mock_context.workspace = workspace

        result = await simulation.simulate(scenario, parameters, mock_context)

        assert isinstance(result, RECPlanningResult)
        # Result uses dict-based structure
        assert "self_consumption_ratio" in result.with_investment
        # Use approximate comparison for floating point
        sc_ratio = result.with_investment["self_consumption_ratio"]
        assert 0.0 <= sc_ratio <= 1.01
        assert "self_sufficiency_ratio" in result.with_investment
        ss_ratio = result.with_investment["self_sufficiency_ratio"]
        assert 0.0 <= ss_ratio <= 1.01

    @pytest.mark.asyncio
    async def test_simulate_with_pv_addition(
        self,
        simulation: RECPlanningSimulation,
        workspace: FileWorkspace,
        mock_context,
    ):
        """Test simulation with PV capacity addition."""
        config = RECScenarioConfig(
            community_id="pv-sim-test",
            reference_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            reference_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
        )
        scenario = await simulation.build_scenario(config, workspace, mock_context)
        mock_context.workspace = workspace

        # Baseline - no additional PV
        baseline_params = RECPlanningParameters(pv_kwp=0.0)
        baseline_result = await simulation.simulate(
            scenario, baseline_params, mock_context
        )

        # With additional PV
        pv_params = RECPlanningParameters(pv_kwp=100.0)
        pv_result = await simulation.simulate(scenario, pv_params, mock_context)

        # Adding PV should increase generation
        assert (
            pv_result.with_investment["total_generation_kwh"]
            > baseline_result.with_investment["total_generation_kwh"]
        )

    @pytest.mark.asyncio
    async def test_simulate_with_battery(
        self,
        simulation: RECPlanningSimulation,
        workspace: FileWorkspace,
        mock_context,
    ):
        """Test simulation with battery storage."""
        config = RECScenarioConfig(
            community_id="battery-test",
            reference_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            reference_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
            assumptions={"existing_pv_kwp": 50.0},  # Need generation to store
        )
        scenario = await simulation.build_scenario(config, workspace, mock_context)
        mock_context.workspace = workspace

        # Without battery
        no_battery_params = RECPlanningParameters(pv_kwp=0.0, battery_kwh=0.0)
        no_battery_result = await simulation.simulate(
            scenario, no_battery_params, mock_context
        )

        # With battery
        battery_params = RECPlanningParameters(pv_kwp=0.0, battery_kwh=100.0)
        battery_result = await simulation.simulate(
            scenario, battery_params, mock_context
        )

        # Battery should improve self-sufficiency (or at least not reduce it)
        assert (
            battery_result.with_investment["self_sufficiency_ratio"]
            >= no_battery_result.with_investment["self_sufficiency_ratio"]
        )

    def test_get_default_parameters(self, simulation: RECPlanningSimulation):
        """Test getting default parameters."""
        params = simulation.get_default_parameters()

        assert isinstance(params, RECPlanningParameters)
        assert params.pv_kwp == 0.0
        assert params.battery_kwh == 0.0

    @pytest.mark.asyncio
    async def test_simulate_returns_recommendations(
        self,
        simulation: RECPlanningSimulation,
        workspace: FileWorkspace,
        mock_context,
    ):
        """Test that simulation returns recommendations."""
        config = RECScenarioConfig(
            community_id="rec-test",
            reference_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            reference_end=datetime(2024, 1, 8, tzinfo=timezone.utc),
        )
        scenario = await simulation.build_scenario(config, workspace, mock_context)
        mock_context.workspace = workspace

        parameters = RECPlanningParameters(pv_kwp=50.0)
        result = await simulation.simulate(scenario, parameters, mock_context)

        assert result.recommendation is not None
        assert result.recommendation.category in ["economics", "error"]


class TestRECScenarioConfig:
    """Tests for RECScenarioConfig model."""

    def test_valid_config(self):
        """Test creating valid config."""
        config = RECScenarioConfig(
            community_id="test",
            reference_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            reference_end=datetime(2024, 12, 31, tzinfo=timezone.utc),
        )

        assert config.community_id == "test"
        assert config.resolution == "1h"  # default

    def test_config_with_custom_resolution(self):
        """Test config with custom resolution."""
        config = RECScenarioConfig(
            community_id="test",
            reference_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            reference_end=datetime(2024, 1, 2, tzinfo=timezone.utc),
            resolution="15min",
        )

        assert config.resolution == "15min"

    def test_config_with_assumptions(self):
        """Test config with assumptions."""
        config = RECScenarioConfig(
            community_id="test",
            reference_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            reference_end=datetime(2024, 1, 2, tzinfo=timezone.utc),
            assumptions={
                "existing_pv_kwp": 100.0,
                "existing_battery_kwh": 50.0,
                "num_participants": 10,
            },
        )

        assert config.assumptions["existing_pv_kwp"] == 100.0


class TestRECPlanningParameters:
    """Tests for RECPlanningParameters model."""

    def test_default_parameters(self):
        """Test default parameter values."""
        params = RECPlanningParameters()

        assert params.pv_kwp == 0.0
        assert params.battery_kwh == 0.0

    def test_custom_parameters(self):
        """Test custom parameter values."""
        params = RECPlanningParameters(
            pv_kwp=100.0,
            battery_kwh=50.0,
        )

        assert params.pv_kwp == 100.0
        assert params.battery_kwh == 50.0

    def test_financial_parameters(self):
        """Test financial parameter defaults."""
        params = RECPlanningParameters()

        assert hasattr(params, "discount_rate")
        assert params.discount_rate == 0.05
        assert hasattr(params, "project_lifetime_years")
        assert params.project_lifetime_years == 25


class TestRECPlanningResult:
    """Tests for RECPlanningResult model."""

    def test_result_structure(self):
        """Test result has expected fields."""
        from celine.dt.modules.rec_planning.models import Recommendation

        result = RECPlanningResult(
            baseline={
                "self_consumption_ratio": 0.5,
                "total_consumption_kwh": 10000.0,
            },
            with_investment={
                "self_consumption_ratio": 0.8,
                "total_consumption_kwh": 10000.0,
                "total_generation_kwh": 8000.0,
                "npv_eur": 5000.0,
            },
            delta={
                "self_consumption_ratio": 0.3,
            },
            recommendation=Recommendation(
                category="economics",
                message="Test",
                pv_kwp=50.0,
                battery_kwh=20.0,
                rationale="Test rationale",
            ),
            grid_import_kwh=3600.0,
        )

        assert result.with_investment["self_consumption_ratio"] == 0.8
        assert result.recommendation.category == "economics"
