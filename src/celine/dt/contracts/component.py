# celine/dt/contracts/component.py
"""
DTComponent contract for reusable computation units.

Components are the building blocks of the Digital Twin. They provide
pure, stateless computations that can be composed by Apps and Simulations.

Key characteristics:
- Pure: same input → same output, no side effects
- Typed: explicit input/output schemas (Pydantic models)
- Composable: can be freely combined
- Internal: not directly exposed via API

Components wrap external libraries (pvlib, RAMP, etc.) or implement
domain-specific calculations (energy balance, economics, etc.).
"""
from __future__ import annotations

from typing import Any, ClassVar, Generic, Protocol, Type, TypeVar, runtime_checkable

from pydantic import BaseModel


I = TypeVar("I", bound=BaseModel)
O = TypeVar("O", bound=BaseModel)


@runtime_checkable
class DTComponent(Protocol[I, O]):
    """
    Digital Twin Component contract.

    A component is a pure, reusable computation unit that transforms
    typed input into typed output. Components should be stateless and
    free of side effects.

    Type Parameters:
        I: Input type (must be a Pydantic BaseModel)
        O: Output type (must be a Pydantic BaseModel)

    Attributes:
        key: Unique identifier in format "module.component-name"
        version: Semantic version string
        input_type: Pydantic model class for input validation
        output_type: Pydantic model class for output structure

    Example:
        class EnergyBalanceInput(BaseModel):
            generation_kwh: list[float]
            consumption_kwh: list[float]

        class EnergyBalanceOutput(BaseModel):
            self_consumption_ratio: float
            self_sufficiency_ratio: float
            grid_import_kwh: float
            grid_export_kwh: float

        class EnergyBalanceComponent(DTComponent[EnergyBalanceInput, EnergyBalanceOutput]):
            key = "energy-balance.calculator"
            version = "1.0.0"

            input_type = EnergyBalanceInput
            output_type = EnergyBalanceOutput

            async def compute(self, input: EnergyBalanceInput, context: RunContext) -> EnergyBalanceOutput:
                # Pure computation logic
                ...
    """

    key: ClassVar[str]
    version: ClassVar[str]

    input_type: Type[I]
    output_type: Type[O]

    async def compute(self, input: I, context: Any) -> O:
        """
        Execute the component computation.

        This method MUST be pure:
        - Deterministic: same input always produces same output
        - Side-effect free: no state mutations, no I/O beyond context.values

        Components may use context.values.fetch() to retrieve data,
        but should not publish events or mutate state.

        Args:
            input: Validated input conforming to input_type schema
            context: RunContext providing access to values service and other components

        Returns:
            Output conforming to output_type schema

        Raises:
            ValueError: If computation fails due to invalid input
            RuntimeError: If computation fails due to internal error
        """
        ...


class ComponentDescriptor:
    """
    Descriptor wrapping a component with metadata.

    Used by the registry to store and retrieve components.
    """

    def __init__(self, component: DTComponent) -> None:
        self.component = component

    @property
    def key(self) -> str:
        return self.component.key

    @property
    def version(self) -> str:
        return self.component.version

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema for component input."""
        return self.component.input_type.model_json_schema()

    @property
    def output_schema(self) -> dict[str, Any]:
        """JSON Schema for component output."""
        return self.component.output_type.model_json_schema()

    def describe(self) -> dict[str, Any]:
        """Return component metadata for API responses."""
        return {
            "key": self.key,
            "version": self.version,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }
