# celine/dt/core/simulation/scenario_store.py
"""Filesystem-backed scenario store.

Persists:
- Metadata at: {scenario_dir}/_scenario_metadata.json
- Scenario data at: {scenario_dir}/_scenario_data.json (Pydantic model dump)

The store returns the raw scenario dict; SimulationRunner is responsible for
parsing it into the simulation.scenario_type.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from celine.dt.contracts.scenario import ScenarioMetadata, ScenarioRef, ScenarioStore
from celine.dt.core.simulation.workspace_layout import SimulationWorkspaceLayout
from celine.dt.core.utils import utc_now

logger = logging.getLogger(__name__)


class FileScenarioStore(ScenarioStore):
    def __init__(self, layout: SimulationWorkspaceLayout) -> None:
        self._layout = layout

    async def get(self, scenario_id: str) -> tuple[ScenarioMetadata, Any] | None:
        meta = await self.get_metadata(scenario_id)
        if meta is None:
            return None
        if meta.expires_at < utc_now():
            return None
        data_path = Path(meta.workspace_path) / "_scenario_data.json"
        if not data_path.exists():
            return meta, None
        scenario_dict = json.loads(data_path.read_text(encoding="utf-8"))
        return meta, scenario_dict

    async def get_metadata(self, scenario_id: str) -> ScenarioMetadata | None:
        for meta_path in self._layout.root.rglob("_scenario_metadata.json"):
            try:
                d = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("scenario_id") != scenario_id:
                continue
            meta = _metadata_from_json(d)
            if meta.expires_at < utc_now():
                return None
            return meta
        return None

    async def put(self, metadata: ScenarioMetadata, scenario: Any) -> ScenarioRef:
        ws = Path(metadata.workspace_path)
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "_scenario_metadata.json").write_text(
            json.dumps(_metadata_to_json(metadata), indent=2),
            encoding="utf-8",
        )
        # scenario may be pydantic model or dict
        if scenario is not None:
            if hasattr(scenario, "model_dump"):
                payload = scenario.model_dump()
            else:
                payload = scenario
            (ws / "_scenario_data.json").write_text(
                json.dumps(payload, indent=2, default=str),
                encoding="utf-8",
            )
        return metadata.to_ref()

    async def delete(self, scenario_id: str) -> bool:
        meta = await self.get_metadata(scenario_id)
        if meta is None:
            return False
        ws = Path(meta.workspace_path)
        if ws.exists():
            import shutil

            shutil.rmtree(ws)
        return True

    async def list(
        self, simulation_key: str | None = None, include_expired: bool = False
    ) -> list[ScenarioRef]:
        refs: list[ScenarioRef] = []
        now = utc_now()
        for meta_path in self._layout.root.rglob("_scenario_metadata.json"):
            try:
                d = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if simulation_key and d.get("simulation_key") != simulation_key:
                continue
            meta = _metadata_from_json(d)
            if not include_expired and meta.expires_at < now:
                continue
            refs.append(meta.to_ref())
        refs.sort(key=lambda r: r.created_at, reverse=True)
        return refs

    async def cleanup_expired(self) -> int:
        now = utc_now()
        count = 0
        for meta_path in list(self._layout.root.rglob("_scenario_metadata.json")):
            try:
                d = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            meta = _metadata_from_json(d)
            if meta.expires_at < now:
                try:
                    import shutil

                    shutil.rmtree(Path(meta.workspace_path))
                    count += 1
                except Exception:
                    logger.exception(
                        "Failed to delete expired scenario %s", meta.scenario_id
                    )
        return count


def _metadata_to_json(m: ScenarioMetadata) -> dict[str, Any]:
    return {
        "simulation_key": m.simulation_key,
        "scenario_id": m.scenario_id,
        "config": m.config,
        "config_hash": m.config_hash,
        "created_at": m.created_at.isoformat(),
        "expires_at": m.expires_at.isoformat(),
        "workspace_path": m.workspace_path,
        "baseline_metrics": m.baseline_metrics,
        "artifacts": m.artifacts,
    }


def _metadata_from_json(d: dict[str, Any]) -> ScenarioMetadata:
    return ScenarioMetadata(
        simulation_key=d["simulation_key"],
        scenario_id=d["scenario_id"],
        config=d.get("config") or {},
        config_hash=d.get("config_hash") or "",
        created_at=datetime.fromisoformat(d["created_at"]),
        expires_at=datetime.fromisoformat(d["expires_at"]),
        workspace_path=d.get("workspace_path") or "",
        baseline_metrics=d.get("baseline_metrics") or {},
        artifacts=d.get("artifacts") or [],
    )
