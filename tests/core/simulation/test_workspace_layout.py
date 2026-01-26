# tests/core/simulation/test_workspace_layout.py
"""Tests for SimulationWorkspaceLayout."""
from __future__ import annotations

import pytest
from pathlib import Path

from celine.dt.core.simulation.workspace_layout import SimulationWorkspaceLayout


class TestSimulationWorkspaceLayout:
    """Tests for SimulationWorkspaceLayout."""

    @pytest.fixture
    def layout(self, tmp_path: Path) -> SimulationWorkspaceLayout:
        """Create a temporary workspace layout."""
        return SimulationWorkspaceLayout(root=tmp_path)

    def test_simulation_root(self, layout: SimulationWorkspaceLayout, tmp_path: Path):
        """Test simulation_root returns correct path."""
        path = layout.simulation_root("my-simulation")

        assert path == tmp_path / "simulations" / "my-simulation"

    def test_scenarios_root(self, layout: SimulationWorkspaceLayout, tmp_path: Path):
        """Test scenarios_root returns correct path."""
        path = layout.scenarios_root("my-simulation")

        assert path == tmp_path / "simulations" / "my-simulation" / "scenarios"

    def test_runs_root(self, layout: SimulationWorkspaceLayout, tmp_path: Path):
        """Test runs_root returns correct path."""
        path = layout.runs_root("my-simulation")

        assert path == tmp_path / "simulations" / "my-simulation" / "runs"

    def test_scenario_dir(self, layout: SimulationWorkspaceLayout, tmp_path: Path):
        """Test scenario_dir returns correct path."""
        path = layout.scenario_dir("my-simulation", "scenario-123")

        expected = (
            tmp_path / "simulations" / "my-simulation" / "scenarios" / "scenario-123"
        )
        assert path == expected

    def test_run_dir(self, layout: SimulationWorkspaceLayout, tmp_path: Path):
        """Test run_dir returns correct path."""
        path = layout.run_dir("my-simulation", "run-456")

        expected = tmp_path / "simulations" / "my-simulation" / "runs" / "run-456"
        assert path == expected

    def test_ensure_simulation_dirs_creates_directories(
        self, layout: SimulationWorkspaceLayout, tmp_path: Path
    ):
        """Test ensure_simulation_dirs creates the required directories."""
        scenarios_dir = layout.scenarios_root("new-simulation")
        runs_dir = layout.runs_root("new-simulation")

        assert not scenarios_dir.exists()
        assert not runs_dir.exists()

        layout.ensure_simulation_dirs("new-simulation")

        assert scenarios_dir.exists()
        assert runs_dir.exists()

    def test_ensure_simulation_dirs_idempotent(self, layout: SimulationWorkspaceLayout):
        """Test ensure_simulation_dirs is idempotent."""
        layout.ensure_simulation_dirs("my-simulation")
        layout.ensure_simulation_dirs("my-simulation")  # Should not raise

        assert layout.scenarios_root("my-simulation").exists()
        assert layout.runs_root("my-simulation").exists()

    def test_different_simulations_have_separate_paths(
        self, layout: SimulationWorkspaceLayout, tmp_path: Path
    ):
        """Test that different simulations have isolated paths."""
        layout.ensure_simulation_dirs("sim-a")
        layout.ensure_simulation_dirs("sim-b")

        scenario_a = layout.scenario_dir("sim-a", "scenario-1")
        scenario_b = layout.scenario_dir("sim-b", "scenario-1")

        assert scenario_a != scenario_b
        assert "sim-a" in str(scenario_a)
        assert "sim-b" in str(scenario_b)

    def test_layout_is_frozen_dataclass(self, layout: SimulationWorkspaceLayout):
        """Test that layout is immutable."""
        with pytest.raises(Exception):  # FrozenInstanceError
            layout.root = Path("/new/path")
