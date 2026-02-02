# celine/dt/core/simulation/workspace_layout.py
"""Filesystem layout for simulation workspaces.

Objectives supported:
- Workspace per simulation (scoped folder)
- Separate scenario cache vs run outputs
- File-based artifacts (parquet/json/bytes)

Layout (root = settings.dt_workspace_root):
  {root}/
    simulations/
      {simulation_key}/
        scenarios/{scenario_id}/...
        runs/{run_id}/...

This module is intentionally simple: it does not attempt to be a database.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SimulationWorkspaceLayout:
    root: Path

    def simulation_root(self, simulation_key: str) -> Path:
        return (self.root / "simulations" / simulation_key).resolve()

    def scenarios_root(self, simulation_key: str) -> Path:
        return self.simulation_root(simulation_key) / "scenarios"

    def runs_root(self, simulation_key: str) -> Path:
        return self.simulation_root(simulation_key) / "runs"

    def scenario_dir(self, simulation_key: str, scenario_id: str) -> Path:
        return self.scenarios_root(simulation_key) / scenario_id

    def run_dir(self, simulation_key: str, run_id: str) -> Path:
        return self.runs_root(simulation_key) / run_id

    def ensure_simulation_dirs(self, simulation_key: str) -> None:
        self.scenarios_root(simulation_key).mkdir(parents=True, exist_ok=True)
        self.runs_root(simulation_key).mkdir(parents=True, exist_ok=True)
