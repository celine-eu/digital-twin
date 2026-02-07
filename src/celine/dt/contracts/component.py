# celine/dt/contracts/component.py
"""
DTComponent contract for reusable, stateless computation units.

Components are the pure building blocks of domain logic. They have no
side effects and can be composed freely by simulations and handlers.
"""
from __future__ import annotations

from typing import Any, ClassVar, Protocol, Type, TypeVar, runtime_checkable

from pydantic import BaseModel

I = TypeVar("I", bound=BaseModel)
O = TypeVar("O", bound=BaseModel)


@runtime_checkable
class DTComponent(Protocol[I, O]):
    """Pure computation unit: same input → same output, no side effects."""

    key: ClassVar[str]
    version: ClassVar[str]

    input_type: Type[I]
    output_type: Type[O]

    async def compute(self, input: I, context: Any) -> O: ...
