from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import yaml

from celine.dt.adapters.base import DatasetAdapter


logger = logging.getLogger(__name__)

DATASET_API_ADAPTER = "dataset-api"


class DatasetSqlApiClient:
    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    async def query(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        # NOTE: Replace endpoint/payload to match your Dataset API.
        # PoC assumes POST /query with {"sql": "...", "params": {...}}
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/query",
                json={"sql": sql, "params": params},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            # Expect either {"rows":[...]} or raw list
            if isinstance(data, dict) and "rows" in data:
                return data["rows"]
            if isinstance(data, list):
                return data
            raise ValueError("Unexpected dataset API response shape")


class DatasetSqlApiAdapter(DatasetAdapter):
    name = DATASET_API_ADAPTER

    def __init__(self, client: DatasetSqlApiClient) -> None:
        self.client = client

    async def query(self, sql: str, params: dict[str, Any]) -> pd.DataFrame:
        res = await self.client.query(sql, params)
        return pd.DataFrame(res)
