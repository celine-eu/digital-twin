from __future__ import annotations
from datetime import datetime
from typing import Generic, Iterable, TypeVar
from pydantic import BaseModel

T = TypeVar("T", int, float)


class TimeSeries(BaseModel):
    timestamps: list[datetime]
    values: list[float]
    unit: str

    def total(self) -> float:
        return float(sum(self.values))

    @classmethod
    def from_rows(
        cls,
        rows: Iterable[dict],
        *,
        time_key: str,
        value_key: str,
        unit: str,
    ) -> "TimeSeries":
        timestamps = []
        values = []

        for row in rows:
            timestamps.append(row[time_key])
            values.append(float(row[value_key]))

        if len(timestamps) != len(values):
            raise ValueError("Mismatched timestamps and values")

        return cls(timestamps=timestamps, values=values, unit=unit)
