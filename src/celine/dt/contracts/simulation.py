# celine/dt/contracts/simulation.py
"""
DTSimulation contract for what-if exploration.

Two-phase execution:
1. ``build_scenario`` – expensive data fetching and baseline computation (cached).
2. ``simulate`` – fast parameter application against the cached scenario.
"""
from __future__ import annotations

from typing import Any, ClassVar, Protocol, Type, TypeVar, runtime_checkable

from pydantic import BaseModel

SC = TypeVar("SC", bound=BaseModel)  # Scenario config
S = TypeVar("S", bound=BaseModel)  # Built scenario
P = TypeVar("P", bound=BaseModel)  # Parameters
R = TypeVar("R", bound=BaseModel)  # Result


@runtime_checkable
class DTSimulation(Protocol[SC, S, P, R]):
    """What-if simulation with scenario caching."""

    key: ClassVar[str]
    version: ClassVar[str]

    scenario_config_type: Type[SC]
    scenario_type: Type[S]
    parameters_type: Type[P]
    result_type: Type[R]

    async def build_scenario(self, config: SC, workspace: Any, context: Any) -> S: ...

    async def simulate(self, scenario: S, parameters: P, context: Any) -> R: ...

    def get_default_parameters(self) -> P: ...


class SimulationDescriptor:
    """Wraps a simulation with schema introspection helpers."""

    def __init__(self, simulation: DTSimulation) -> None:  # type: ignore[type-arg]
        self.simulation = simulation

    @property
    def key(self) -> str:
        return self.simulation.key

    @property
    def version(self) -> str:
        return self.simulation.version

    def describe(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "version": self.version,
            "scenario_config_schema": self.simulation.scenario_config_type.model_json_schema(),
            "parameters_schema": self.simulation.parameters_type.model_json_schema(),
            "result_schema": self.simulation.result_type.model_json_schema(),
        }
