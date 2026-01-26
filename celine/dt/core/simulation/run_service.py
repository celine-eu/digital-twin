# celine/dt/core/simulation/run_service.py
"""Run persistence and workspace handling (filesystem-backed).

Implementation notes:
- Metadata is stored as JSON at: {run_dir}/_run_metadata.json
- Result (if any) is stored at: {run_dir}/results/result.json
- Artifacts are any files under the run directory, excluding metadata
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from celine.dt.contracts.run import RunMetadata, RunRef, RunStatus, RunStore
from celine.dt.core.simulation.workspace import FileWorkspace
from celine.dt.core.simulation.workspace_layout import SimulationWorkspaceLayout

logger = logging.getLogger(__name__)


def compute_parameters_hash(parameters: dict[str, Any]) -> str:
    payload = json.dumps(parameters, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class FileRunStore(RunStore):
    def __init__(self, layout: SimulationWorkspaceLayout) -> None:
        self._layout = layout

    async def get_metadata(self, run_id: str) -> RunMetadata | None:
        # Run id alone is insufficient to locate without index;
        # we therefore scan. This is acceptable for dev and small deployments.
        for meta_path in self._layout.root.rglob("_run_metadata.json"):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if data.get("run_id") == run_id:
                return _metadata_from_json(data)
        return None

    async def put_metadata(self, metadata: RunMetadata) -> None:
        meta_path = Path(metadata.workspace_path) / "_run_metadata.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(_metadata_to_json(metadata), indent=2), encoding="utf-8")

    async def list(
        self,
        simulation_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RunRef]:
        refs: list[RunRef] = []
        for meta_path in self._layout.root.rglob("_run_metadata.json"):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if simulation_key and data.get("simulation_key") != simulation_key:
                continue
            md = _metadata_from_json(data)
            refs.append(md.to_ref())

        refs.sort(key=lambda r: r.created_at, reverse=True)
        return refs[offset : offset + limit]


class RunService:
    def __init__(self, store: RunStore, layout: SimulationWorkspaceLayout) -> None:
        self._store = store
        self._layout = layout

    def create_workspace(self, simulation_key: str, run_id: str | None = None) -> FileWorkspace:
        if run_id is None:
            run_id = str(uuid.uuid4())
        self._layout.ensure_simulation_dirs(simulation_key)
        path = self._layout.run_dir(simulation_key, run_id)
        return FileWorkspace(run_id, path)

    async def create_run(
        self,
        simulation_key: str,
        scenario_id: str,
        parameters: dict[str, Any],
        workspace: FileWorkspace,
    ) -> RunMetadata:
        now = datetime.utcnow()
        md = RunMetadata(
            simulation_key=simulation_key,
            run_id=workspace.id,
            scenario_id=scenario_id,
            parameters=parameters,
            parameters_hash=compute_parameters_hash(parameters),
            created_at=now,
            status=RunStatus.queued,
            workspace_path=str(workspace.path),
        )
        await self._store.put_metadata(md)
        return md

    async def update_status(
        self,
        md: RunMetadata,
        *,
        status: RunStatus,
        error: str | None = None,
    ) -> RunMetadata:
        if status == RunStatus.running and md.started_at is None:
            md.started_at = datetime.utcnow()
        if status in (RunStatus.completed, RunStatus.failed) and md.finished_at is None:
            md.finished_at = datetime.utcnow()
        md.status = status
        md.error = error
        # refresh artifacts list
        ws = FileWorkspace(md.run_id, Path(md.workspace_path))
        md.artifacts = await ws.list_files()
        await self._store.put_metadata(md)
        return md

    async def get_metadata(self, run_id: str) -> RunMetadata | None:
        return await self._store.get_metadata(run_id)

    async def list_runs(self, simulation_key: str | None = None, limit: int = 100, offset: int = 0) -> list[RunRef]:
        return await self._store.list(simulation_key=simulation_key, limit=limit, offset=offset)

    async def write_result(self, md: RunMetadata, result: dict[str, Any]) -> None:
        ws = FileWorkspace(md.run_id, Path(md.workspace_path))
        await ws.write_json("results/result.json", result)


def _metadata_to_json(md: RunMetadata) -> dict[str, Any]:
    d = asdict(md)
    # datetimes/enums -> strings
    d["created_at"] = md.created_at.isoformat()
    d["started_at"] = md.started_at.isoformat() if md.started_at else None
    d["finished_at"] = md.finished_at.isoformat() if md.finished_at else None
    d["status"] = md.status.value
    return d


def _metadata_from_json(d: dict[str, Any]) -> RunMetadata:
    return RunMetadata(
        simulation_key=d["simulation_key"],
        run_id=d["run_id"],
        scenario_id=d["scenario_id"],
        parameters=d.get("parameters") or {},
        parameters_hash=d.get("parameters_hash") or compute_parameters_hash(d.get("parameters") or {}),
        created_at=datetime.fromisoformat(d["created_at"]),
        started_at=datetime.fromisoformat(d["started_at"]) if d.get("started_at") else None,
        finished_at=datetime.fromisoformat(d["finished_at"]) if d.get("finished_at") else None,
        status=RunStatus(d.get("status") or RunStatus.queued.value),
        error=d.get("error"),
        workspace_path=d.get("workspace_path") or "",
        artifacts=d.get("artifacts") or [],
    )
