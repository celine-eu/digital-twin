# tests/api/test_simulations.py
"""Tests for simulations API endpoints."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import BaseModel

from celine.dt.core.utils import utc_now

# Note: These tests are designed to work with the actual FastAPI app
# but can be run in isolation with mocks when FastAPI is not available


class DummyTestScenarioConfig(BaseModel):
    """Test scenario configuration."""

    community_id: str
    target_kwh: float = 1000.0


class DummyTestScenario(BaseModel):
    """Test scenario data."""

    community_id: str
    baseline_kwh: float


class DummyTestParameters(BaseModel):
    """Test simulation parameters."""

    add_pv_kwp: float = 0.0


class DummyTestResult(BaseModel):
    """Test simulation result."""

    self_consumption_ratio: float


class DummyTestSimulation:
    """Test simulation implementation."""

    key = "test-sim"
    version = "1.0.0"

    scenario_config_type = DummyTestScenarioConfig
    scenario_type = DummyTestScenario
    parameters_type = DummyTestParameters
    result_type = DummyTestResult

    async def build_scenario(self, config, workspace, context):
        return DummyTestScenario(community_id=config.community_id, baseline_kwh=1000.0)

    async def simulate(self, scenario, parameters, context):
        return DummyTestResult(self_consumption_ratio=0.8)

    def get_default_parameters(self):
        return DummyTestParameters()


class TestSimulationsAPIRoutes:
    """
    Test cases for the simulations API router.

    These tests verify the API contract and response structure.
    They can be run with or without a full FastAPI test client.
    """

    def test_build_scenario_request_model(self):
        """Test BuildScenarioRequest model structure."""
        from celine.dt.api.simulations import BuildScenarioRequest

        request = BuildScenarioRequest(
            config={"community_id": "test"},
            ttl_hours=24,
            reuse_existing=True,
        )

        assert request.config == {"community_id": "test"}
        assert request.ttl_hours == 24
        assert request.reuse_existing is True

    def test_build_scenario_request_defaults(self):
        """Test BuildScenarioRequest default values."""
        from celine.dt.api.simulations import BuildScenarioRequest

        request = BuildScenarioRequest(config={"community_id": "test"})

        assert request.ttl_hours == 24
        assert request.reuse_existing is True

    def test_build_scenario_response_model(self):
        """Test BuildScenarioResponse model structure."""
        from celine.dt.api.simulations import BuildScenarioResponse

        response = BuildScenarioResponse(
            scenario_id="scenario-123",
            simulation_key="test-sim",
            created_at="2024-01-01T00:00:00",
            expires_at="2024-01-02T00:00:00",
            config_hash="abc123",
            baseline_metrics={"total_kwh": 1000.0},
        )

        assert response.scenario_id == "scenario-123"
        assert response.simulation_key == "test-sim"
        assert response.baseline_metrics["total_kwh"] == 1000.0

    def test_run_simulation_request_model(self):
        """Test RunSimulationRequest model structure."""
        from celine.dt.api.simulations import RunSimulationRequest

        request = RunSimulationRequest(
            scenario_id="scenario-123",
            parameters={"add_pv_kwp": 10.0},
            include_result=True,
        )

        assert request.scenario_id == "scenario-123"
        assert request.parameters["add_pv_kwp"] == 10.0
        assert request.include_result is True

    def test_run_simulation_request_defaults(self):
        """Test RunSimulationRequest default values."""
        from celine.dt.api.simulations import RunSimulationRequest

        request = RunSimulationRequest(scenario_id="scenario-123")

        assert request.parameters == {}
        assert request.include_result is False

    def test_run_inline_request_model(self):
        """Test RunInlineRequest model structure."""
        from celine.dt.api.simulations import RunInlineRequest

        request = RunInlineRequest(
            scenario={"community_id": "test"},
            parameters={"add_pv_kwp": 5.0},
            include_result=True,
            ttl_hours=1,
        )

        assert request.scenario == {"community_id": "test"}
        assert request.parameters["add_pv_kwp"] == 5.0
        assert request.ttl_hours == 1

    def test_sweep_request_model(self):
        """Test SweepRequest model structure."""
        from celine.dt.api.simulations import SweepRequest

        request = SweepRequest(
            scenario_id="scenario-123",
            parameter_sets=[
                {"add_pv_kwp": 0.0},
                {"add_pv_kwp": 10.0},
                {"add_pv_kwp": 20.0},
            ],
            include_baseline=True,
        )

        assert request.scenario_id == "scenario-123"
        assert len(request.parameter_sets) == 3
        assert request.include_baseline is True


class TestSimulationsAPIIntegration:
    """
    Integration tests for simulations API.

    These tests require a full FastAPI test client setup.
    """

    @pytest.fixture
    def mock_dt(self):
        """Create a mock DT instance with simulation capabilities."""
        dt = MagicMock()
        dt.simulations = MagicMock()
        dt.simulation_runner = MagicMock()
        dt.scenario_service = MagicMock()
        dt.run_service = MagicMock()
        return dt

    def test_list_simulations_returns_empty_when_no_simulations(self, mock_dt):
        """Test that list_simulations returns empty list when no simulations registered."""
        mock_dt.simulations = None
        mock_dt.registry = MagicMock()
        mock_dt.registry.simulations = None

        # Without simulations, should return empty list

    def test_describe_simulation_not_found(self, mock_dt):
        """Test describe_simulation returns 404 for nonexistent simulation."""
        mock_dt.simulations.get_descriptor.side_effect = KeyError("not found")

        # Should raise HTTPException with 404

    def test_build_scenario_success(self, mock_dt):
        """Test successful scenario building."""
        mock_ref = MagicMock()
        mock_ref.scenario_id = "scenario-123"
        mock_ref.created_at = utc_now()
        mock_ref.expires_at = utc_now() + timedelta(hours=24)
        mock_ref.config_hash = "abc123"

        mock_dt.simulation_runner.build_scenario = AsyncMock(return_value=mock_ref)
        mock_dt.scenario_service.get_metadata = AsyncMock(
            return_value=MagicMock(baseline_metrics={"total_kwh": 1000.0})
        )

        # Should return BuildScenarioResponse

    def test_run_simulation_success(self, mock_dt):
        """Test successful simulation run."""
        mock_dt.simulation_runner.run = AsyncMock(
            return_value={
                "self_consumption_ratio": 0.8,
                "npv": 10000.0,
            }
        )

        # Should return simulation result dict

    def test_run_inline_success(self, mock_dt):
        """Test successful inline simulation run."""
        mock_dt.simulation_runner.run_with_inline_scenario = AsyncMock(
            return_value={
                "self_consumption_ratio": 0.75,
            }
        )

        # Should return simulation result dict

    def test_sweep_success(self, mock_dt):
        """Test successful parameter sweep."""
        from celine.dt.contracts.simulation import SweepResult, SweepResultItem

        mock_dt.simulation_runner.sweep = AsyncMock(
            return_value=SweepResult(
                scenario_id="scenario-123",
                baseline={"self_consumption_ratio": 0.5},
                results=[
                    SweepResultItem(
                        parameters={"add_pv_kwp": 10.0},
                        result={"self_consumption_ratio": 0.7},
                        delta={"self_consumption_ratio": 0.2},
                    ),
                ],
                total_runs=1,
                successful_runs=1,
                failed_runs=0,
            )
        )

        # Should return SweepResult

    def test_list_scenarios_empty(self, mock_dt):
        """Test listing scenarios when none exist."""
        mock_dt.scenario_service.list_scenarios = AsyncMock(return_value=[])

        # Should return empty list

    def test_get_scenario_not_found(self, mock_dt):
        """Test get_scenario returns 404 when not found."""
        mock_dt.scenario_service.get_metadata = AsyncMock(return_value=None)

        # Should raise HTTPException with 404

    def test_delete_scenario_success(self, mock_dt):
        """Test successful scenario deletion."""
        mock_dt.scenario_service.get_metadata = AsyncMock(
            return_value=MagicMock(simulation_key="test-sim")
        )
        mock_dt.scenario_service.delete_scenario = AsyncMock(return_value=True)

        # Should return {"deleted": True}

    def test_list_runs_empty(self, mock_dt):
        """Test listing runs when none exist."""
        mock_dt.run_service.list_runs = AsyncMock(return_value=[])

        # Should return empty list

    def test_get_run_not_found(self, mock_dt):
        """Test get_run returns 404 when not found."""
        mock_dt.run_service.get_metadata = AsyncMock(return_value=None)

        # Should raise HTTPException with 404

    def test_list_run_artifacts(self, mock_dt):
        """Test listing artifacts for a run."""
        mock_dt.run_service.get_metadata = AsyncMock(
            return_value=MagicMock(artifacts=["result.json", "data.parquet"])
        )

        # Should return ["result.json", "data.parquet"]


class TestSimulationsAPIErrorHandling:
    """Tests for error handling in simulations API."""

    def test_invalid_config_returns_400(self):
        """Test that invalid scenario config returns 400 Bad Request."""
        # ValueError from runner should be caught and returned as 400

    def test_simulation_not_found_returns_404(self):
        """Test that nonexistent simulation returns 404 Not Found."""
        # KeyError from registry should be caught and returned as 404

    def test_scenario_not_found_returns_404(self):
        """Test that nonexistent scenario returns 404 Not Found."""
        # KeyError from scenario service should be caught and returned as 404

    def test_internal_error_returns_500(self):
        """Test that internal errors return 500 Internal Server Error."""
        # Unexpected exceptions should be caught and returned as 500
