# celine/dt/core/simulation/scenario.py
"""Scenario service for managing cached simulation contexts.

Key properties:
- Scenario is expensive, cacheable (data fetch + baseline)
- Scenario artifacts live on disk (parquet/json/etc.)
- Metadata and scenario object are persisted (filesystem store)

The ScenarioStore returns raw scenario dict; SimulationRunner is responsible
for parsing into the simulation.scenario_type for strong typing.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from celine.dt.contracts.scenario import ScenarioMetadata, ScenarioRef, ScenarioStore
from celine.dt.core.simulation.workspace import FileWorkspace
from celine.dt.core.simulation.workspace_layout import SimulationWorkspaceLayout

logger = logging.getLogger(__name__)


def compute_config_hash(config: dict[str, Any]) -> str:
    """Deterministic hash of scenario configuration for cache reuse."""
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class ScenarioService:
    """High-level service for scenario management."""

    def __init__(
        self,
        *,
        store: ScenarioStore,
        layout: SimulationWorkspaceLayout,
        default_ttl_hours: int = 24,
    ) -> None:
        self._store = store
        self._layout = layout
        self._default_ttl_hours = default_ttl_hours

    def create_workspace(self, simulation_key: str, scenario_id: str | None = None) -> FileWorkspace:
        if scenario_id is None:
            scenario_id = str(uuid.uuid4())
        self._layout.ensure_simulation_dirs(simulation_key)
        path = self._layout.scenario_dir(simulation_key, scenario_id)
        return FileWorkspace(scenario_id, path)

    async def create_scenario(
        self,
        *,
        simulation_key: str,
        config: dict[str, Any],
        scenario_data: Any,
        workspace: FileWorkspace,
        baseline_metrics: dict[str, Any] | None = None,
        ttl_hours: int | None = None,
    ) -> ScenarioRef:
        scenario_id = workspace.id
        now = datetime.utcnow()
        ttl = ttl_hours or self._default_ttl_hours

        artifacts = await workspace.list_files()

        metadata = ScenarioMetadata(
            simulation_key=simulation_key,
            scenario_id=scenario_id,
            config=config,
            config_hash=compute_config_hash(config),
            created_at=now,
            expires_at=now + timedelta(hours=ttl),
            workspace_path=str(workspace.path),
            baseline_metrics=baseline_metrics or {},
            artifacts=artifacts,
        )

        ref = await self._store.put(metadata, scenario_data)
        logger.info(
            "Created scenario %s for simulation %s (TTL: %d hours)",
            scenario_id,
            simulation_key,
            ttl,
        )
        return ref

    async def get_scenario(self, scenario_id: str) -> tuple[ScenarioMetadata, dict[str, Any] | None] | None:
        entry = await self._store.get(scenario_id)
        if entry is None:
            return None
        metadata, scenario_payload = entry
        if isinstance(scenario_payload, dict) or scenario_payload is None:
            return metadata, scenario_payload
        # safety: if a store returns a pydantic model, dump to dict
        if hasattr(scenario_payload, "model_dump"):
            return metadata, scenario_payload.model_dump()
        return metadata, dict(scenario_payload)

    async def get_metadata(self, scenario_id: str) -> ScenarioMetadata | None:
        return await self._store.get_metadata(scenario_id)

    async def get_workspace(self, scenario_id: str) -> FileWorkspace | None:
        md = await self.get_metadata(scenario_id)
        if md is None:
            return None
        return FileWorkspace(md.scenario_id, Path(md.workspace_path))

    async def delete_scenario(self, scenario_id: str) -> bool:
        return await self._store.delete(scenario_id)

    async def list_scenarios(self, simulation_key: str | None = None, include_expired: bool = False) -> list[ScenarioRef]:
        return await self._store.list(simulation_key=simulation_key, include_expired=include_expired)

    async def cleanup_expired(self) -> int:
        return await self._store.cleanup_expired()

    async def find_by_config_hash(self, simulation_key: str, config_hash: str) -> ScenarioRef | None:
        refs = await self.list_scenarios(simulation_key=simulation_key, include_expired=False)
        for ref in refs:
            if ref.config_hash == config_hash and not ref.is_expired():
                return ref
        return None
