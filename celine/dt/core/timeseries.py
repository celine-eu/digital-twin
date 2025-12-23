
from __future__ import annotations
from typing import Generic, TypeVar, Sequence
from pydantic import BaseModel, Field

T = TypeVar("T", int, float)

class TimeSeries(BaseModel, Generic[T]):
    values: Sequence[T]
    timestep_hours: float = Field(gt=0)

    def total(self) -> float:
        return float(sum(self.values))
