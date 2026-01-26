# celine/dt/contracts/workspace.py
"""
Workspace contract for simulation artifact storage.

A Workspace provides temporary storage for simulation artifacts such as:
- Fetched data (parquet files)
- Computed intermediates (baselines, profiles)
- Cached results

Workspaces are scoped to a scenario and cleaned up when the scenario expires.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from celine.dt.core.utils import utc_now


@runtime_checkable
class Workspace(Protocol):
    """
    Temporary storage for simulation artifacts.

    Workspaces provide a sandboxed directory for simulations to store
    intermediate data. This enables:
    - Caching expensive data fetches
    - Storing computed baselines
    - Sharing data between scenario setup and simulation runs
    - Reproducibility (scenario + params = deterministic result)

    Workspace paths are relative to the workspace root. Use simple names
    like "consumption.parquet" or "weather/hourly.parquet".
    """

    @property
    def id(self) -> str:
        """Unique workspace identifier."""
        ...

    @property
    def path(self) -> Path:
        """Root directory for this workspace."""
        ...

    @property
    def created_at(self) -> datetime:
        """When the workspace was created."""
        ...

    async def write_parquet(self, name: str, data: Any) -> Path:
        """
        Write data as a parquet file.

        Args:
            name: Relative path (e.g., "consumption.parquet")
            data: DataFrame or compatible data structure

        Returns:
            Absolute path to the written file
        """
        ...

    async def read_parquet(self, name: str) -> Any:
        """
        Read a parquet file.

        Args:
            name: Relative path (e.g., "consumption.parquet")

        Returns:
            DataFrame or compatible data structure

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        ...

    async def write_json(self, name: str, data: dict[str, Any]) -> Path:
        """
        Write JSON data.

        Args:
            name: Relative path (e.g., "metadata.json")
            data: JSON-serializable dictionary

        Returns:
            Absolute path to the written file
        """
        ...

    async def read_json(self, name: str) -> dict[str, Any]:
        """
        Read JSON data.

        Args:
            name: Relative path (e.g., "metadata.json")

        Returns:
            Parsed JSON dictionary

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        ...

    async def write_bytes(self, name: str, data: bytes) -> Path:
        """
        Write raw bytes.

        Args:
            name: Relative path
            data: Raw bytes

        Returns:
            Absolute path to the written file
        """
        ...

    async def read_bytes(self, name: str) -> bytes:
        """
        Read raw bytes.

        Args:
            name: Relative path

        Returns:
            Raw bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        ...

    async def exists(self, name: str) -> bool:
        """
        Check if an artifact exists.

        Args:
            name: Relative path

        Returns:
            True if file exists, False otherwise
        """
        ...

    async def list_files(self, prefix: str = "") -> list[str]:
        """
        List files in the workspace.

        Args:
            prefix: Optional path prefix to filter by

        Returns:
            List of relative file paths
        """
        ...

    async def delete(self, name: str) -> bool:
        """
        Delete an artifact.

        Args:
            name: Relative path

        Returns:
            True if deleted, False if didn't exist
        """
        ...

    async def cleanup(self) -> None:
        """
        Remove all workspace contents and the workspace directory.

        Called when the scenario expires or is explicitly deleted.
        """
        ...


class WorkspaceBase(ABC):
    """
    Abstract base class for workspace implementations.

    Provides common functionality and enforces the Workspace protocol.
    """

    def __init__(self, workspace_id: str, root_path: Path) -> None:
        self._id = workspace_id
        self._path = root_path
        self._created_at = utc_now()

    @property
    def id(self) -> str:
        return self._id

    @property
    def path(self) -> Path:
        return self._path

    @property
    def created_at(self) -> datetime:
        return self._created_at

    def _resolve_path(self, name: str) -> Path:
        """
        Resolve a relative name to an absolute path.

        Ensures the path stays within the workspace root (security).
        """
        resolved = (self._path / name).resolve()

        # Security check: ensure path is within workspace
        if not str(resolved).startswith(str(self._path.resolve())):
            raise ValueError(f"Path '{name}' escapes workspace root")

        return resolved

    @abstractmethod
    async def write_parquet(self, name: str, data: Any) -> Path: ...

    @abstractmethod
    async def read_parquet(self, name: str) -> Any: ...

    @abstractmethod
    async def write_json(self, name: str, data: dict[str, Any]) -> Path: ...

    @abstractmethod
    async def read_json(self, name: str) -> dict[str, Any]: ...

    @abstractmethod
    async def write_bytes(self, name: str, data: bytes) -> Path: ...

    @abstractmethod
    async def read_bytes(self, name: str) -> bytes: ...

    @abstractmethod
    async def exists(self, name: str) -> bool: ...

    @abstractmethod
    async def list_files(self, prefix: str = "") -> list[str]: ...

    @abstractmethod
    async def delete(self, name: str) -> bool: ...

    @abstractmethod
    async def cleanup(self) -> None: ...
