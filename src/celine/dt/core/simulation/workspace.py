# celine/dt/core/simulation/workspace.py
"""
Workspace implementation for simulation artifact storage.

Provides file-based storage for simulation artifacts including
parquet files, JSON metadata, and raw bytes.
"""
from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from celine.dt.contracts.workspace import WorkspaceBase

logger = logging.getLogger(__name__)


class FileWorkspace(WorkspaceBase):
    """
    File-based workspace implementation.

    Stores artifacts in a directory structure under a configurable root.
    Supports parquet, JSON, and raw bytes storage.

    Directory structure:
        {root}/
            {workspace_id}/
                consumption.parquet
                weather.parquet
                metadata.json
                ...
    """

    def __init__(self, workspace_id: str, root_path: Path) -> None:
        super().__init__(workspace_id, root_path)

        # Ensure workspace directory exists
        self._path.mkdir(parents=True, exist_ok=True)
        logger.debug("Created workspace: %s at %s", workspace_id, root_path)

    async def write_parquet(self, name: str, data: Any) -> Path:
        """Write data as parquet file."""
        try:
            import pandas as pd
        except ImportError:
            raise RuntimeError("pandas is required for parquet support")

        path = self._resolve_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, pd.DataFrame):
            data.to_parquet(path, index=True)
        elif hasattr(data, "to_pandas"):
            # Support polars or similar
            data.to_pandas().to_parquet(path, index=True)
        else:
            # Try to convert to DataFrame
            df = pd.DataFrame(data)
            df.to_parquet(path, index=True)

        logger.debug("Wrote parquet: %s", path)
        return path

    async def read_parquet(self, name: str) -> Any:
        """Read parquet file as DataFrame."""
        try:
            import pandas as pd
        except ImportError:
            raise RuntimeError("pandas is required for parquet support")

        path = self._resolve_path(name)

        if not path.exists():
            raise FileNotFoundError(f"Parquet file not found: {name}")

        df = pd.read_parquet(path)
        logger.debug("Read parquet: %s (%d rows)", path, len(df))
        return df

    async def write_json(self, name: str, data: dict[str, Any]) -> Path:
        """Write JSON data."""
        path = self._resolve_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

        logger.debug("Wrote JSON: %s", path)
        return path

    async def read_json(self, name: str) -> dict[str, Any]:
        """Read JSON data."""
        path = self._resolve_path(name)

        if not path.exists():
            raise FileNotFoundError(f"JSON file not found: {name}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        logger.debug("Read JSON: %s", path)
        return data

    async def write_bytes(self, name: str, data: bytes) -> Path:
        """Write raw bytes."""
        path = self._resolve_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "wb") as f:
            f.write(data)

        logger.debug("Wrote bytes: %s (%d bytes)", path, len(data))
        return path

    async def read_bytes(self, name: str) -> bytes:
        """Read raw bytes."""
        path = self._resolve_path(name)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {name}")

        with open(path, "rb") as f:
            data = f.read()

        logger.debug("Read bytes: %s (%d bytes)", path, len(data))
        return data

    async def exists(self, name: str) -> bool:
        """Check if file exists."""
        path = self._resolve_path(name)
        return path.exists()

    async def list_files(self, prefix: str = "") -> list[str]:
        """List files in workspace."""
        if prefix:
            search_path = self._resolve_path(prefix)
        else:
            search_path = self._path

        if not search_path.exists():
            return []

        files = []
        for path in search_path.rglob("*"):
            if path.is_file():
                # Return path relative to workspace root
                rel_path = path.relative_to(self._path)
                files.append(str(rel_path))

        return sorted(files)

    async def delete(self, name: str) -> bool:
        """Delete a file."""
        path = self._resolve_path(name)

        if not path.exists():
            return False

        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)

        logger.debug("Deleted: %s", path)
        return True

    async def cleanup(self) -> None:
        """Remove entire workspace."""
        if self._path.exists():
            shutil.rmtree(self._path)
            logger.info("Cleaned up workspace: %s", self._id)


class WorkspaceManager:
    """
    Manager for creating and tracking workspaces.

    Provides workspace lifecycle management including creation,
    retrieval, and cleanup of expired workspaces.
    """

    def __init__(self, root_path: Path | str) -> None:
        """
        Initialize workspace manager.

        Args:
            root_path: Root directory for all workspaces
        """
        self._root = Path(root_path)
        self._root.mkdir(parents=True, exist_ok=True)
        self._workspaces: dict[str, FileWorkspace] = {}

        logger.info("WorkspaceManager initialized at %s", self._root)

    def create(self, workspace_id: str | None = None) -> FileWorkspace:
        """
        Create a new workspace.

        Args:
            workspace_id: Optional custom ID (auto-generated if not provided)

        Returns:
            New workspace instance
        """
        if workspace_id is None:
            workspace_id = str(uuid.uuid4())

        if workspace_id in self._workspaces:
            raise ValueError(f"Workspace '{workspace_id}' already exists")

        workspace_path = self._root / workspace_id
        workspace = FileWorkspace(workspace_id, workspace_path)

        self._workspaces[workspace_id] = workspace
        return workspace

    def get(self, workspace_id: str) -> FileWorkspace | None:
        """
        Get an existing workspace.

        Args:
            workspace_id: Workspace identifier

        Returns:
            Workspace instance or None if not found
        """
        # Check in-memory cache first
        if workspace_id in self._workspaces:
            return self._workspaces[workspace_id]

        # Check if workspace directory exists on disk
        workspace_path = self._root / workspace_id
        if workspace_path.exists():
            workspace = FileWorkspace(workspace_id, workspace_path)
            self._workspaces[workspace_id] = workspace
            return workspace

        return None

    def get_or_create(self, workspace_id: str) -> FileWorkspace:
        """
        Get existing workspace or create new one.

        Args:
            workspace_id: Workspace identifier

        Returns:
            Workspace instance
        """
        workspace = self.get(workspace_id)
        if workspace is None:
            workspace = self.create(workspace_id)
        return workspace

    async def delete(self, workspace_id: str) -> bool:
        """
        Delete a workspace and all its contents.

        Args:
            workspace_id: Workspace identifier

        Returns:
            True if deleted, False if not found
        """
        workspace = self.get(workspace_id)
        if workspace is None:
            return False

        await workspace.cleanup()
        del self._workspaces[workspace_id]
        return True

    def list(self) -> list[str]:
        """
        List all workspace IDs.

        Returns:
            List of workspace identifiers
        """
        # Include both in-memory and on-disk workspaces
        disk_workspaces = {d.name for d in self._root.iterdir() if d.is_dir()}
        memory_workspaces = set(self._workspaces.keys())
        return sorted(disk_workspaces | memory_workspaces)

    @property
    def root_path(self) -> Path:
        """Root directory for workspaces."""
        return self._root
