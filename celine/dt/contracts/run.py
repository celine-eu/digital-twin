# celine/dt/contracts/run.py
"""Run contracts for simulation execution tracking.

A Run is an immutable execution instance identified by run_id.

Key requirement:
- Results reachable via API using simulation run ID
- Run artifacts stored on disk (parquet/json/etc.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


@dataclass(frozen=True)
class RunRef:
    simulation_key: str
    run_id: str
    scenario_id: str
    created_at: datetime
    status: RunStatus


@dataclass
class RunMetadata:
    simulation_key: str
    run_id: str
    scenario_id: str
    parameters: dict[str, Any]
    parameters_hash: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: RunStatus = RunStatus.queued
    error: str | None = None
    workspace_path: str = ""
    artifacts: list[str] = field(default_factory=list)

    def to_ref(self) -> RunRef:
        return RunRef(
            simulation_key=self.simulation_key,
            run_id=self.run_id,
            scenario_id=self.scenario_id,
            created_at=self.created_at,
            status=self.status,
        )


@runtime_checkable
class RunStore(Protocol):
    async def get_metadata(self, run_id: str) -> RunMetadata | None: ...
    async def put_metadata(self, metadata: RunMetadata) -> None: ...
    async def list(
        self,
        simulation_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RunRef]: ...
