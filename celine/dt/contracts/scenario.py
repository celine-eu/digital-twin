# celine/dt/contracts/scenario.py
"""
Scenario contracts for simulation context management.

A Scenario represents an immutable data context that simulations run against.
Scenarios are expensive to build (data fetching, baseline computation) but
can be cached and reused for multiple simulation runs with different parameters.

This enables efficient parameter sweeps and what-if exploration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel


S_co = TypeVar("S_co", bound=BaseModel, covariant=True)


@dataclass(frozen=True)
class ScenarioRef:
    """
    Reference to a cached scenario.

    This is the lightweight handle returned when a scenario is created.
    It contains metadata but not the scenario data itself.
    """

    simulation_key: str
    scenario_id: str
    created_at: datetime
    expires_at: datetime
    workspace_path: str
    config_hash: str

    def is_expired(self) -> bool:
        """Check if the scenario has expired."""
        return datetime.utcnow() > self.expires_at

    def time_remaining(self) -> timedelta:
        """Time until expiration (may be negative if expired)."""
        return self.expires_at - datetime.utcnow()


@dataclass
class ScenarioMetadata:
    """
    Metadata about a scenario.

    Stored alongside the scenario for introspection and management.
    """

    simulation_key: str
    scenario_id: str
    config: dict[str, Any]
    config_hash: str
    created_at: datetime
    expires_at: datetime
    workspace_path: str
    baseline_metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)

    def to_ref(self) -> ScenarioRef:
        """Convert to a lightweight reference."""
        return ScenarioRef(
            simulation_key=self.simulation_key,
            scenario_id=self.scenario_id,
            created_at=self.created_at,
            expires_at=self.expires_at,
            workspace_path=self.workspace_path,
            config_hash=self.config_hash,
        )


@runtime_checkable
class ScenarioStore(Protocol):
    """
    Protocol for scenario persistence.

    Implementations may store scenarios in memory, on disk, or in a database.
    """

    async def get(self, scenario_id: str) -> tuple[ScenarioMetadata, Any] | None:
        """
        Retrieve a scenario by ID.

        Args:
            scenario_id: Unique scenario identifier

        Returns:
            Tuple of (metadata, scenario_data) or None if not found
        """
        ...

    async def get_metadata(self, scenario_id: str) -> ScenarioMetadata | None:
        """
        Retrieve only scenario metadata (lightweight).

        Args:
            scenario_id: Unique scenario identifier

        Returns:
            Metadata or None if not found
        """
        ...

    async def put(
        self,
        metadata: ScenarioMetadata,
        scenario: Any,
    ) -> ScenarioRef:
        """
        Store a scenario.

        Args:
            metadata: Scenario metadata
            scenario: The scenario object (Pydantic model)

        Returns:
            Reference to the stored scenario
        """
        ...

    async def delete(self, scenario_id: str) -> bool:
        """
        Delete a scenario and its workspace.

        Args:
            scenario_id: Unique scenario identifier

        Returns:
            True if deleted, False if not found
        """
        ...

    async def list(
        self,
        simulation_key: str | None = None,
        include_expired: bool = False,
    ) -> list[ScenarioRef]:
        """
        List scenarios.

        Args:
            simulation_key: Filter by simulation (optional)
            include_expired: Include expired scenarios

        Returns:
            List of scenario references
        """
        ...

    async def cleanup_expired(self) -> int:
        """
        Remove all expired scenarios and their workspaces.

        Returns:
            Number of scenarios removed
        """
        ...


@runtime_checkable
class ScenarioBuilder(Protocol[S_co]):
    """
    Protocol for building scenarios.

    This is typically implemented by DTSimulation.build_scenario().
    """

    async def build(
        self,
        config: Any,
        workspace: Any,
        context: Any,
    ) -> S_co:
        """
        Build a scenario from configuration.

        Args:
            config: Scenario configuration
            workspace: Workspace for storing artifacts
            context: RunContext for data fetching

        Returns:
            Built scenario object
        """
        ...


