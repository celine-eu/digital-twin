# tests/core/simulation/test_workspace.py
"""Tests for FileWorkspace and WorkspaceManager."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from celine.dt.core.simulation.workspace import FileWorkspace, WorkspaceManager


class TestFileWorkspace:
    """Tests for FileWorkspace."""

    @pytest.fixture
    def workspace(self, tmp_path: Path) -> FileWorkspace:
        """Create a temporary workspace."""
        return FileWorkspace("test-workspace", tmp_path / "test-workspace")

    def test_workspace_creates_directory(self, tmp_path: Path):
        """Test that workspace creates its directory on init."""
        workspace_path = tmp_path / "new-workspace"

        assert not workspace_path.exists()

        workspace = FileWorkspace("new-ws", workspace_path)

        assert workspace_path.exists()
        assert workspace.id == "new-ws"
        assert workspace.path == workspace_path

    @pytest.mark.asyncio
    async def test_write_and_read_json(self, workspace: FileWorkspace):
        """Test writing and reading JSON files."""
        data = {"key": "value", "number": 42, "nested": {"a": 1}}

        path = await workspace.write_json("test.json", data)

        assert path.exists()

        read_data = await workspace.read_json("test.json")

        assert read_data == data

    @pytest.mark.asyncio
    async def test_write_json_creates_subdirectories(self, workspace: FileWorkspace):
        """Test that write_json creates nested directories."""
        data = {"test": True}

        path = await workspace.write_json("deep/nested/dir/file.json", data)

        assert path.exists()
        assert "deep/nested/dir" in str(path)

    @pytest.mark.asyncio
    async def test_read_json_not_found_raises(self, workspace: FileWorkspace):
        """Test that reading nonexistent JSON raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await workspace.read_json("nonexistent.json")

    @pytest.mark.asyncio
    async def test_write_and_read_bytes(self, workspace: FileWorkspace):
        """Test writing and reading raw bytes."""
        data = b"binary data \x00\x01\x02"

        path = await workspace.write_bytes("data.bin", data)

        assert path.exists()

        read_data = await workspace.read_bytes("data.bin")

        assert read_data == data

    @pytest.mark.asyncio
    async def test_read_bytes_not_found_raises(self, workspace: FileWorkspace):
        """Test that reading nonexistent bytes raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await workspace.read_bytes("nonexistent.bin")

    @pytest.mark.asyncio
    async def test_exists(self, workspace: FileWorkspace):
        """Test exists() method."""
        assert not await workspace.exists("test.json")

        await workspace.write_json("test.json", {"data": 1})

        assert await workspace.exists("test.json")
        assert not await workspace.exists("other.json")

    @pytest.mark.asyncio
    async def test_list_files_empty(self, workspace: FileWorkspace):
        """Test list_files on empty workspace."""
        files = await workspace.list_files()

        assert files == []

    @pytest.mark.asyncio
    async def test_list_files(self, workspace: FileWorkspace):
        """Test listing files in workspace."""
        await workspace.write_json("file1.json", {})
        await workspace.write_json("subdir/file2.json", {})
        await workspace.write_bytes("data.bin", b"test")

        files = await workspace.list_files()

        assert len(files) == 3
        assert "file1.json" in files
        assert "subdir/file2.json" in files
        assert "data.bin" in files

    @pytest.mark.asyncio
    async def test_list_files_with_prefix(self, workspace: FileWorkspace):
        """Test listing files with prefix filter."""
        await workspace.write_json("baseline/consumption.json", {})
        await workspace.write_json("baseline/generation.json", {})
        await workspace.write_json("results/output.json", {})

        baseline_files = await workspace.list_files("baseline")
        result_files = await workspace.list_files("results")

        assert len(baseline_files) == 2
        assert len(result_files) == 1

    @pytest.mark.asyncio
    async def test_delete_file(self, workspace: FileWorkspace):
        """Test deleting a file."""
        await workspace.write_json("to_delete.json", {})

        assert await workspace.exists("to_delete.json")

        deleted = await workspace.delete("to_delete.json")

        assert deleted
        assert not await workspace.exists("to_delete.json")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, workspace: FileWorkspace):
        """Test deleting nonexistent file returns False."""
        deleted = await workspace.delete("nonexistent.json")

        assert not deleted

    @pytest.mark.asyncio
    async def test_cleanup(self, workspace: FileWorkspace, tmp_path: Path):
        """Test cleanup removes workspace directory."""
        await workspace.write_json("file.json", {})

        assert workspace.path.exists()

        await workspace.cleanup()

        assert not workspace.path.exists()


class TestWorkspaceManager:
    """Tests for WorkspaceManager."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> WorkspaceManager:
        """Create a temporary workspace manager."""
        return WorkspaceManager(tmp_path / "workspaces")

    def test_manager_creates_root_directory(self, tmp_path: Path):
        """Test that manager creates its root directory."""
        root = tmp_path / "new-root"

        assert not root.exists()

        manager = WorkspaceManager(root)

        assert root.exists()
        assert manager.root_path == root

    def test_create_workspace(self, manager: WorkspaceManager):
        """Test creating a new workspace."""
        workspace = manager.create("test-ws")

        assert workspace.id == "test-ws"
        assert workspace.path.exists()
        assert workspace.path.parent == manager.root_path

    def test_create_workspace_auto_id(self, manager: WorkspaceManager):
        """Test creating workspace with auto-generated ID."""
        workspace = manager.create()

        assert workspace.id  # Should have a UUID
        assert len(workspace.id) == 36  # UUID string length

    def test_create_duplicate_raises(self, manager: WorkspaceManager):
        """Test that creating duplicate workspace raises ValueError."""
        manager.create("duplicate")

        with pytest.raises(ValueError, match="already exists"):
            manager.create("duplicate")

    def test_get_workspace(self, manager: WorkspaceManager):
        """Test getting an existing workspace."""
        original = manager.create("test-ws")

        retrieved = manager.get("test-ws")

        assert retrieved is original

    def test_get_nonexistent_returns_none(self, manager: WorkspaceManager):
        """Test getting nonexistent workspace returns None."""
        result = manager.get("nonexistent")

        assert result is None

    def test_get_restores_from_disk(self, manager: WorkspaceManager):
        """Test that get() restores workspace from disk if not in memory."""
        workspace = manager.create("disk-ws")
        workspace_path = workspace.path

        # Clear internal cache
        manager._workspaces.clear()

        # Should restore from disk
        restored = manager.get("disk-ws")

        assert restored is not None
        assert restored.path == workspace_path

    def test_get_or_create_existing(self, manager: WorkspaceManager):
        """Test get_or_create returns existing workspace."""
        original = manager.create("existing")

        retrieved = manager.get_or_create("existing")

        assert retrieved is original

    def test_get_or_create_new(self, manager: WorkspaceManager):
        """Test get_or_create creates new workspace."""
        workspace = manager.get_or_create("new-ws")

        assert workspace.id == "new-ws"
        assert manager.get("new-ws") is workspace

    @pytest.mark.asyncio
    async def test_delete_workspace(self, manager: WorkspaceManager):
        """Test deleting a workspace."""
        workspace = manager.create("to-delete")
        workspace_path = workspace.path

        assert workspace_path.exists()

        deleted = await manager.delete("to-delete")

        assert deleted
        assert not workspace_path.exists()
        assert manager.get("to-delete") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, manager: WorkspaceManager):
        """Test deleting nonexistent workspace returns False."""
        deleted = await manager.delete("nonexistent")

        assert not deleted

    def test_list_workspaces(self, manager: WorkspaceManager):
        """Test listing all workspaces."""
        manager.create("ws-1")
        manager.create("ws-2")
        manager.create("ws-3")

        workspaces = manager.list()

        assert len(workspaces) == 3
        assert set(workspaces) == {"ws-1", "ws-2", "ws-3"}
