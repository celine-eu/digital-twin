from __future__ import annotations

from datetime import datetime
from typing import Protocol, Any

import pandas as pd


class DatasetAdapter(Protocol):
    name: str

    async def fetch_rec_structure(self, rec_id: str) -> dict[str, Any]:
        ...

    async def fetch_timeseries(
        self, rec_id: str, start: datetime, end: datetime, granularity: str
    ) -> pd.DataFrame:
        ...
