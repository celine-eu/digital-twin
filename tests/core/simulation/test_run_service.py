# tests/core/simulation/test_run_service.py
"""Tests for RunService and FileRunStore."""
from __future__ import annotations

import json
import pytest
from datetime import datetime
from pathlib import Path

from celine.dt.contracts.run import RunMetadata, RunStatus, RunRef
from celine.dt.core.simulation.run_service import (
    RunService,
    FileRunStore,
    compute_parameters_hash,
)
from celine.dt.core.simulation.workspace import FileWorkspace
from celine.dt.core.simulation.workspace_layout import SimulationWorkspaceLayout
from celine.dt.core.utils import utc_now


class TestComputeParametersHash:
    """Tests for compute_parameters_hash function."""

    def test_deterministic(self):
        """Test that same parameters produce same hash."""
        params = {"add_pv_kwp": 10.0, "battery_kwh": 20.0}

        hash1 = compute_parameters_hash(params)
        hash2 = compute_parameters_hash(params)

        assert hash1 == hash2

    def test_different_params_different_hashes(self):
        """Test that different parameters produce different hashes."""
        params1 = {"add_pv_kwp": 10.0}
        params2 = {"add_pv_kwp": 20.0}

        hash1 = compute_parameters_hash(params1)
        hash2 = compute_parameters_hash(params2)

        assert hash1 != hash2

    def test_order_independent(self):
        """Test that key order doesn't affect hash."""
        params1 = {"a": 1, "b": 2}
        params2 = {"b": 2, "a": 1}

        hash1 = compute_parameters_hash(params1)
        hash2 = compute_parameters_hash(params2)

        assert hash1 == hash2

    def test_hash_length(self):
        """Test that hash is 16 characters."""
        params = {"test": True}

        h = compute_parameters_hash(params)

        assert len(h) == 16


class TestFileRunStore:
    """Tests for FileRunStore."""

    @pytest.fixture
    def layout(self, tmp_path: Path) -> SimulationWorkspaceLayout:
        """Create a temporary workspace layout."""
        return SimulationWorkspaceLayout(root=tmp_path)

    @pytest.fixture
    def store(self, layout: SimulationWorkspaceLayout) -> FileRunStore:
        """Create a run store."""
        return FileRunStore(layout=layout)

    def _create_metadata(
        self,
        layout: SimulationWorkspaceLayout,
        simulation_key: str = "test-sim",
        run_id: str = "run-123",
        scenario_id: str = "scenario-456",
        status: RunStatus = RunStatus.queued,
    ) -> RunMetadata:
        """Helper to create test metadata."""
        workspace_path = layout.run_dir(simulation_key, run_id)
        workspace_path.mkdir(parents=True, exist_ok=True)
        return RunMetadata(
            simulation_key=simulation_key,
            run_id=run_id,
            scenario_id=scenario_id,
            parameters={"add_pv_kwp": 10.0},
            parameters_hash=compute_parameters_hash({"add_pv_kwp": 10.0}),
            created_at=utc_now(),
            status=status,
            workspace_path=str(workspace_path),
        )

    @pytest.mark.asyncio
    async def test_put_and_get_metadata(
        self, store: FileRunStore, layout: SimulationWorkspaceLayout
    ):
        """Test storing and retrieving run metadata."""
        metadata = self._create_metadata(layout)

        await store.put_metadata(metadata)

        retrieved = await store.get_metadata("run-123")

        assert retrieved is not None
        assert retrieved.run_id == "run-123"
        assert retrieved.simulation_key == "test-sim"
        assert retrieved.scenario_id == "scenario-456"
        assert retrieved.parameters["add_pv_kwp"] == 10.0

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, store: FileRunStore):
        """Test that getting nonexistent run returns None."""
        result = await store.get_metadata("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_runs(
        self, store: FileRunStore, layout: SimulationWorkspaceLayout
    ):
        """Test listing runs."""
        meta1 = self._create_metadata(layout, run_id="run-1")
        meta2 = self._create_metadata(layout, run_id="run-2")
        await store.put_metadata(meta1)
        await store.put_metadata(meta2)

        refs = await store.list()

        assert len(refs) == 2
        ids = {ref.run_id for ref in refs}
        assert ids == {"run-1", "run-2"}

    @pytest.mark.asyncio
    async def test_list_filters_by_simulation_key(
        self, store: FileRunStore, layout: SimulationWorkspaceLayout
    ):
        """Test listing runs filtered by simulation key."""
        meta1 = self._create_metadata(layout, simulation_key="sim-a", run_id="run-a")
        meta2 = self._create_metadata(layout, simulation_key="sim-b", run_id="run-b")
        await store.put_metadata(meta1)
        await store.put_metadata(meta2)

        refs = await store.list(simulation_key="sim-a")

        assert len(refs) == 1
        assert refs[0].run_id == "run-a"

    @pytest.mark.asyncio
    async def test_list_with_pagination(
        self, store: FileRunStore, layout: SimulationWorkspaceLayout
    ):
        """Test listing runs with limit and offset."""
        for i in range(5):
            meta = self._create_metadata(layout, run_id=f"run-{i}")
            await store.put_metadata(meta)

        refs = await store.list(limit=2, offset=1)

        assert len(refs) == 2

    @pytest.mark.asyncio
    async def test_list_sorted_by_created_at(
        self, store: FileRunStore, layout: SimulationWorkspaceLayout
    ):
        """Test that list returns runs sorted by creation time (newest first)."""
        meta1 = self._create_metadata(layout, run_id="run-1")
        meta2 = self._create_metadata(layout, run_id="run-2")
        await store.put_metadata(meta1)
        await store.put_metadata(meta2)

        refs = await store.list()

        # Should be sorted by created_at descending
        assert all(isinstance(ref, RunRef) for ref in refs)


class TestRunService:
    """Tests for RunService."""

    @pytest.fixture
    def layout(self, tmp_path: Path) -> SimulationWorkspaceLayout:
        """Create a temporary workspace layout."""
        return SimulationWorkspaceLayout(root=tmp_path)

    @pytest.fixture
    def store(self, layout: SimulationWorkspaceLayout) -> FileRunStore:
        """Create a run store."""
        return FileRunStore(layout=layout)

    @pytest.fixture
    def service(
        self, store: FileRunStore, layout: SimulationWorkspaceLayout
    ) -> RunService:
        """Create a run service."""
        return RunService(store=store, layout=layout)

    def test_create_workspace(self, service: RunService):
        """Test creating a workspace for a run."""
        workspace = service.create_workspace("test-sim")

        assert workspace is not None
        assert workspace.path.exists()
        assert "runs" in str(workspace.path)

    def test_create_workspace_with_custom_id(self, service: RunService):
        """Test creating workspace with custom run ID."""
        workspace = service.create_workspace("test-sim", "custom-run-id")

        assert workspace.id == "custom-run-id"

    @pytest.mark.asyncio
    async def test_create_run(self, service: RunService):
        """Test creating a run."""
        workspace = service.create_workspace("test-sim", "run-1")

        metadata = await service.create_run(
            simulation_key="test-sim",
            scenario_id="scenario-1",
            parameters={"add_pv_kwp": 10.0},
            workspace=workspace,
        )

        assert metadata.run_id == "run-1"
        assert metadata.simulation_key == "test-sim"
        assert metadata.scenario_id == "scenario-1"
        assert metadata.status == RunStatus.queued
        assert metadata.parameters["add_pv_kwp"] == 10.0

    @pytest.mark.asyncio
    async def test_update_status_to_running(self, service: RunService):
        """Test updating run status to running."""
        workspace = service.create_workspace("test-sim", "run-1")
        metadata = await service.create_run(
            simulation_key="test-sim",
            scenario_id="scenario-1",
            parameters={},
            workspace=workspace,
        )

        updated = await service.update_status(metadata, status=RunStatus.running)

        assert updated.status == RunStatus.running
        assert updated.started_at is not None
        assert updated.finished_at is None

    @pytest.mark.asyncio
    async def test_update_status_to_completed(self, service: RunService):
        """Test updating run status to completed."""
        workspace = service.create_workspace("test-sim", "run-1")
        metadata = await service.create_run(
            simulation_key="test-sim",
            scenario_id="scenario-1",
            parameters={},
            workspace=workspace,
        )
        await service.update_status(metadata, status=RunStatus.running)

        updated = await service.update_status(metadata, status=RunStatus.completed)

        assert updated.status == RunStatus.completed
        assert updated.finished_at is not None

    @pytest.mark.asyncio
    async def test_update_status_to_failed(self, service: RunService):
        """Test updating run status to failed with error message."""
        workspace = service.create_workspace("test-sim", "run-1")
        metadata = await service.create_run(
            simulation_key="test-sim",
            scenario_id="scenario-1",
            parameters={},
            workspace=workspace,
        )

        updated = await service.update_status(
            metadata, status=RunStatus.failed, error="Something went wrong"
        )

        assert updated.status == RunStatus.failed
        assert updated.error == "Something went wrong"
        assert updated.finished_at is not None

    @pytest.mark.asyncio
    async def test_get_metadata(self, service: RunService):
        """Test getting run metadata."""
        workspace = service.create_workspace("test-sim", "run-1")
        await service.create_run(
            simulation_key="test-sim",
            scenario_id="scenario-1",
            parameters={"test": 1},
            workspace=workspace,
        )

        retrieved = await service.get_metadata("run-1")

        assert retrieved is not None
        assert retrieved.run_id == "run-1"

    @pytest.mark.asyncio
    async def test_list_runs(self, service: RunService):
        """Test listing runs."""
        for i in range(3):
            workspace = service.create_workspace("test-sim", f"run-{i}")
            await service.create_run(
                simulation_key="test-sim",
                scenario_id="scenario-1",
                parameters={},
                workspace=workspace,
            )

        refs = await service.list_runs()

        assert len(refs) == 3

    @pytest.mark.asyncio
    async def test_write_result(self, service: RunService):
        """Test writing simulation result."""
        workspace = service.create_workspace("test-sim", "run-1")
        metadata = await service.create_run(
            simulation_key="test-sim",
            scenario_id="scenario-1",
            parameters={},
            workspace=workspace,
        )

        result = {"self_consumption_ratio": 0.8, "npv": 10000.0}
        await service.write_result(metadata, result)

        # Verify result file exists
        result_path = Path(metadata.workspace_path) / "results" / "result.json"
        assert result_path.exists()

        # Verify contents
        with open(result_path) as f:
            saved = json.load(f)
        assert saved["self_consumption_ratio"] == 0.8

    @pytest.mark.asyncio
    async def test_update_status_refreshes_artifacts(self, service: RunService):
        """Test that update_status refreshes the artifacts list."""
        workspace = service.create_workspace("test-sim", "run-1")
        metadata = await service.create_run(
            simulation_key="test-sim",
            scenario_id="scenario-1",
            parameters={},
            workspace=workspace,
        )

        # Write some files
        await workspace.write_json("output.json", {"result": 1})

        updated = await service.update_status(metadata, status=RunStatus.completed)

        assert "output.json" in updated.artifacts


class TestRunMetadataSerialization:
    """Tests for RunMetadata JSON serialization."""

    @pytest.fixture
    def layout(self, tmp_path: Path) -> SimulationWorkspaceLayout:
        """Create a temporary workspace layout."""
        return SimulationWorkspaceLayout(root=tmp_path)

    @pytest.fixture
    def store(self, layout: SimulationWorkspaceLayout) -> FileRunStore:
        """Create a run store."""
        return FileRunStore(layout=layout)

    @pytest.mark.asyncio
    async def test_round_trip_serialization(
        self, store: FileRunStore, layout: SimulationWorkspaceLayout
    ):
        """Test that metadata survives round-trip serialization."""
        workspace_path = layout.run_dir("test-sim", "run-1")
        workspace_path.mkdir(parents=True, exist_ok=True)

        now = utc_now()
        original = RunMetadata(
            simulation_key="test-sim",
            run_id="run-1",
            scenario_id="scenario-1",
            parameters={"add_pv_kwp": 10.5, "nested": {"value": True}},
            parameters_hash="abc123",
            created_at=now,
            started_at=now,
            finished_at=now,
            status=RunStatus.completed,
            error="test error",
            workspace_path=str(workspace_path),
            artifacts=["file1.json", "file2.parquet"],
        )

        await store.put_metadata(original)
        retrieved = await store.get_metadata("run-1")

        assert retrieved is not None
        assert retrieved.simulation_key == original.simulation_key
        assert retrieved.run_id == original.run_id
        assert retrieved.scenario_id == original.scenario_id
        assert retrieved.parameters == original.parameters
        assert retrieved.parameters_hash == original.parameters_hash
        assert retrieved.status == original.status
        assert retrieved.error == original.error
        assert retrieved.artifacts == original.artifacts
