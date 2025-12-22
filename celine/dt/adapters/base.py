from __future__ import annotations

from datetime import datetime
from typing import Protocol, Any

import pandas as pd


class DatasetAdapter(Protocol):
    name: str

    async def query(self, sql: str, params: dict[str, Any]) -> pd.DataFrame: ...
