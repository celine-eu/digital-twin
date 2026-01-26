# tests/core/simulation/test_scenario.py
"""Tests for ScenarioService and FileScenarioStore."""
from __future__ import annotations

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from celine.dt.contracts.scenario import ScenarioMetadata, ScenarioRef
from celine.dt.core.simulation.scenario import ScenarioService, compute_config_hash
from celine.dt.core.simulation.scenario_store import FileScenarioStore
from celine.dt.core.simulation.workspace import FileWorkspace
from celine.dt.core.simulation.workspace_layout import SimulationWorkspaceLayout
from celine.dt.core.utils import utc_now


class TestComputeConfigHash:
    """Tests for compute_config_hash function."""

    def test_deterministic(self):
        """Test that same config produces same hash."""
        config = {"community_id": "test", "value": 42}

        hash1 = compute_config_hash(config)
        hash2 = compute_config_hash(config)

        assert hash1 == hash2

    def test_different_configs_different_hashes(self):
        """Test that different configs produce different hashes."""
        config1 = {"community_id": "test1"}
        config2 = {"community_id": "test2"}

        hash1 = compute_config_hash(config1)
        hash2 = compute_config_hash(config2)

        assert hash1 != hash2

    def test_order_independent(self):
        """Test that key order doesn't affect hash."""
        config1 = {"a": 1, "b": 2}
        config2 = {"b": 2, "a": 1}

        hash1 = compute_config_hash(config1)
        hash2 = compute_config_hash(config2)

        assert hash1 == hash2

    def test_hash_length(self):
        """Test that hash is 16 characters."""
        config = {"test": True}

        h = compute_config_hash(config)

        assert len(h) == 16


class TestFileScenarioStore:
    """Tests for FileScenarioStore."""

    @pytest.fixture
    def layout(self, tmp_path: Path) -> SimulationWorkspaceLayout:
        """Create a temporary workspace layout."""
        return SimulationWorkspaceLayout(root=tmp_path)

    @pytest.fixture
    def store(self, layout: SimulationWorkspaceLayout) -> FileScenarioStore:
        """Create a scenario store."""
        return FileScenarioStore(layout=layout)

    def _create_metadata(
        self,
        layout: SimulationWorkspaceLayout,
        simulation_key: str = "test-sim",
        scenario_id: str = "scenario-123",
        ttl_hours: int = 24,
    ) -> ScenarioMetadata:
        """Helper to create test metadata."""
        now = utc_now()
        workspace_path = layout.scenario_dir(simulation_key, scenario_id)
        return ScenarioMetadata(
            simulation_key=simulation_key,
            scenario_id=scenario_id,
            config={"community_id": "test"},
            config_hash=compute_config_hash({"community_id": "test"}),
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
            workspace_path=str(workspace_path),
            baseline_metrics={"total_kwh": 1000.0},
            artifacts=["baseline.json"],
        )

    @pytest.mark.asyncio
    async def test_put_and_get(
        self, store: FileScenarioStore, layout: SimulationWorkspaceLayout
    ):
        """Test storing and retrieving a scenario."""
        metadata = self._create_metadata(layout)
        scenario_data = {"community_id": "test", "total_kwh": 1000.0}

        ref = await store.put(metadata, scenario_data)

        assert ref.scenario_id == "scenario-123"
        assert ref.simulation_key == "test-sim"

        # Retrieve
        result = await store.get("scenario-123")

        assert result is not None
        retrieved_meta, retrieved_data = result
        assert retrieved_meta.scenario_id == "scenario-123"
        assert retrieved_data["community_id"] == "test"

    @pytest.mark.asyncio
    async def test_get_metadata(
        self, store: FileScenarioStore, layout: SimulationWorkspaceLayout
    ):
        """Test retrieving only metadata."""
        metadata = self._create_metadata(layout)
        await store.put(metadata, {"test": True})

        retrieved = await store.get_metadata("scenario-123")

        assert retrieved is not None
        assert retrieved.scenario_id == "scenario-123"
        assert retrieved.baseline_metrics["total_kwh"] == 1000.0

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, store: FileScenarioStore):
        """Test that getting nonexistent scenario returns None."""
        result = await store.get("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_expired_returns_none(
        self, store: FileScenarioStore, layout: SimulationWorkspaceLayout
    ):
        """Test that getting expired scenario returns None."""
        metadata = self._create_metadata(layout, ttl_hours=-1)  # Already expired
        await store.put(metadata, {"test": True})

        result = await store.get("scenario-123")

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_scenario(
        self, store: FileScenarioStore, layout: SimulationWorkspaceLayout
    ):
        """Test deleting a scenario."""
        metadata = self._create_metadata(layout)
        await store.put(metadata, {"test": True})

        deleted = await store.delete("scenario-123")

        assert deleted
        assert await store.get("scenario-123") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, store: FileScenarioStore):
        """Test deleting nonexistent scenario returns False."""
        deleted = await store.delete("nonexistent")

        assert not deleted

    @pytest.mark.asyncio
    async def test_list_scenarios(
        self, store: FileScenarioStore, layout: SimulationWorkspaceLayout
    ):
        """Test listing scenarios."""
        meta1 = self._create_metadata(layout, scenario_id="scenario-1")
        meta2 = self._create_metadata(layout, scenario_id="scenario-2")
        await store.put(meta1, {"id": 1})
        await store.put(meta2, {"id": 2})

        refs = await store.list()

        assert len(refs) == 2
        ids = {ref.scenario_id for ref in refs}
        assert ids == {"scenario-1", "scenario-2"}

    @pytest.mark.asyncio
    async def test_list_filters_by_simulation_key(
        self, store: FileScenarioStore, layout: SimulationWorkspaceLayout
    ):
        """Test listing scenarios filtered by simulation key."""
        meta1 = self._create_metadata(
            layout, simulation_key="sim-a", scenario_id="scenario-a"
        )
        meta2 = self._create_metadata(
            layout, simulation_key="sim-b", scenario_id="scenario-b"
        )
        await store.put(meta1, {"id": "a"})
        await store.put(meta2, {"id": "b"})

        refs = await store.list(simulation_key="sim-a")

        assert len(refs) == 1
        assert refs[0].scenario_id == "scenario-a"

    @pytest.mark.asyncio
    async def test_list_excludes_expired_by_default(
        self, store: FileScenarioStore, layout: SimulationWorkspaceLayout
    ):
        """Test that list excludes expired scenarios by default."""
        valid = self._create_metadata(layout, scenario_id="valid")
        expired = self._create_metadata(layout, scenario_id="expired", ttl_hours=-1)
        await store.put(valid, {"valid": True})
        await store.put(expired, {"expired": True})

        refs = await store.list(include_expired=False)

        assert len(refs) == 1
        assert refs[0].scenario_id == "valid"

    @pytest.mark.asyncio
    async def test_list_includes_expired_when_requested(
        self, store: FileScenarioStore, layout: SimulationWorkspaceLayout
    ):
        """Test that list can include expired scenarios."""
        valid = self._create_metadata(layout, scenario_id="valid")
        expired = self._create_metadata(layout, scenario_id="expired", ttl_hours=-1)
        await store.put(valid, {"valid": True})
        await store.put(expired, {"expired": True})

        refs = await store.list(include_expired=True)

        assert len(refs) == 2

    @pytest.mark.asyncio
    async def test_cleanup_expired(
        self, store: FileScenarioStore, layout: SimulationWorkspaceLayout
    ):
        """Test cleanup_expired removes expired scenarios."""
        valid = self._create_metadata(layout, scenario_id="valid")
        expired = self._create_metadata(layout, scenario_id="expired", ttl_hours=-1)
        await store.put(valid, {"valid": True})
        await store.put(expired, {"expired": True})

        count = await store.cleanup_expired()

        assert count == 1
        assert await store.get("valid") is not None
        # The workspace directory should be deleted for expired


class TestScenarioService:
    """Tests for ScenarioService."""

    @pytest.fixture
    def layout(self, tmp_path: Path) -> SimulationWorkspaceLayout:
        """Create a temporary workspace layout."""
        return SimulationWorkspaceLayout(root=tmp_path)

    @pytest.fixture
    def store(self, layout: SimulationWorkspaceLayout) -> FileScenarioStore:
        """Create a scenario store."""
        return FileScenarioStore(layout=layout)

    @pytest.fixture
    def service(
        self, store: FileScenarioStore, layout: SimulationWorkspaceLayout
    ) -> ScenarioService:
        """Create a scenario service."""
        return ScenarioService(store=store, layout=layout, default_ttl_hours=24)

    def test_create_workspace(self, service: ScenarioService):
        """Test creating a workspace for a scenario."""
        workspace = service.create_workspace("test-sim")

        assert workspace is not None
        assert workspace.path.exists()
        assert "scenarios" in str(workspace.path)

    def test_create_workspace_with_custom_id(self, service: ScenarioService):
        """Test creating workspace with custom scenario ID."""
        workspace = service.create_workspace("test-sim", "custom-id")

        assert workspace.id == "custom-id"

    @pytest.mark.asyncio
    async def test_create_scenario(self, service: ScenarioService):
        """Test creating a scenario through the service."""
        workspace = service.create_workspace("test-sim", "scenario-1")

        ref = await service.create_scenario(
            simulation_key="test-sim",
            config={"community_id": "test"},
            scenario_data={"total_kwh": 1000.0},
            workspace=workspace,
            baseline_metrics={"metric1": 1.0},
        )

        assert ref.scenario_id == "scenario-1"
        assert ref.simulation_key == "test-sim"
        assert not ref.is_expired()

    @pytest.mark.asyncio
    async def test_get_scenario(self, service: ScenarioService):
        """Test getting a scenario through the service."""
        workspace = service.create_workspace("test-sim", "scenario-1")
        await service.create_scenario(
            simulation_key="test-sim",
            config={"community_id": "test"},
            scenario_data={"total_kwh": 1000.0},
            workspace=workspace,
        )

        result = await service.get_scenario("scenario-1")

        assert result is not None
        metadata, data = result
        assert metadata.scenario_id == "scenario-1"
        assert data is not None and data["total_kwh"] == 1000.0

    @pytest.mark.asyncio
    async def test_get_workspace(self, service: ScenarioService):
        """Test getting workspace for a scenario."""
        original_ws = service.create_workspace("test-sim", "scenario-1")
        await service.create_scenario(
            simulation_key="test-sim",
            config={},
            scenario_data={},
            workspace=original_ws,
        )

        retrieved_ws = await service.get_workspace("scenario-1")

        assert retrieved_ws is not None
        assert retrieved_ws.path == original_ws.path

    @pytest.mark.asyncio
    async def test_find_by_config_hash(self, service: ScenarioService):
        """Test finding scenario by config hash."""
        workspace = service.create_workspace("test-sim", "scenario-1")
        config = {"community_id": "test", "value": 42}
        await service.create_scenario(
            simulation_key="test-sim",
            config=config,
            scenario_data={},
            workspace=workspace,
        )

        found = await service.find_by_config_hash(
            "test-sim", compute_config_hash(config)
        )

        assert found is not None
        assert found.scenario_id == "scenario-1"

    @pytest.mark.asyncio
    async def test_find_by_config_hash_not_found(self, service: ScenarioService):
        """Test find_by_config_hash returns None when not found."""
        found = await service.find_by_config_hash("test-sim", "nonexistent-hash")

        assert found is None

    @pytest.mark.asyncio
    async def test_list_scenarios(self, service: ScenarioService):
        """Test listing scenarios through the service."""
        for i in range(3):
            workspace = service.create_workspace("test-sim", f"scenario-{i}")
            await service.create_scenario(
                simulation_key="test-sim",
                config={"id": i},
                scenario_data={},
                workspace=workspace,
            )

        refs = await service.list_scenarios()

        assert len(refs) == 3

    @pytest.mark.asyncio
    async def test_delete_scenario(self, service: ScenarioService):
        """Test deleting a scenario through the service."""
        workspace = service.create_workspace("test-sim", "to-delete")
        await service.create_scenario(
            simulation_key="test-sim",
            config={},
            scenario_data={},
            workspace=workspace,
        )

        deleted = await service.delete_scenario("to-delete")

        assert deleted
        assert await service.get_scenario("to-delete") is None
