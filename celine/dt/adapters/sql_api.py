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


@dataclass
class MappingConfig:
    load_query: str
    pv_query: str
    tariff_query: str | None = None


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
    name = "dataset-sql-api"

    def __init__(self, client: DatasetSqlApiClient, mapping_path: str) -> None:
        self.client = client
        self.mapping = self._load_mapping(mapping_path)

    def _load_mapping(self, path: str) -> MappingConfig:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Mapping file not found: {path}")
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        sql = cfg.get("sql", {})
        return MappingConfig(
            load_query=sql["load_query"],
            pv_query=sql["pv_query"],
            tariff_query=sql.get("tariff_query"),
        )

    async def fetch_rec_structure(self, rec_id: str) -> dict[str, Any]:
        # PoC: structure is optional for sizing. Return minimal.
        return {"rec_id": rec_id}

    async def fetch_timeseries(
        self, rec_id: str, start: datetime, end: datetime, granularity: str
    ) -> pd.DataFrame:
        params = {
            "rec_id": rec_id,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "granularity": granularity,
        }
        load_rows = await self.client.query(self.mapping.load_query, params)
        pv_rows = await self.client.query(self.mapping.pv_query, params)

        load_df = pd.DataFrame(load_rows)
        pv_df = pd.DataFrame(pv_rows)

        if load_df.empty or pv_df.empty:
            logger.warning("Empty timeseries fetched", extra={"rec_id": rec_id})
        # expected columns: ts, load_kw / pv_kw
        # Normalize
        for df, col in [(load_df, "load_kw"), (pv_df, "pv_kw")]:
            if "ts" not in df.columns:
                raise ValueError("Dataset query must return 'ts' column")
            if col not in df.columns:
                # accept value column
                if "value" in df.columns:
                    df[col] = df["value"]
                else:
                    raise ValueError(f"Dataset query must return '{col}' or 'value'")

            df["ts"] = pd.to_datetime(df["ts"], utc=True)

        merged = pd.merge(
            load_df[["ts", "load_kw"]], pv_df[["ts", "pv_kw"]], on="ts", how="outer"
        ).fillna(0.0)

        if self.mapping.tariff_query:
            tariff_rows = await self.client.query(self.mapping.tariff_query, params)
            tariff_df = pd.DataFrame(tariff_rows)
            if not tariff_df.empty:
                tariff_df["ts"] = pd.to_datetime(tariff_df["ts"], utc=True)
                merged = pd.merge(merged, tariff_df, on="ts", how="left")
        # Ensure columns exist
        if "import_price_eur_per_kwh" not in merged.columns:
            merged["import_price_eur_per_kwh"] = 0.0
        if "export_price_eur_per_kwh" not in merged.columns:
            merged["export_price_eur_per_kwh"] = 0.0

        merged = merged.sort_values("ts").reset_index(drop=True)
        return merged
