from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from fastapi import APIRouter

from celine.dt.adapters.base import DatasetAdapter
from celine.dt.core.registry import DTApp

from celine.dt.apps.battery_sizing.models import (
    BatterySizingScenario,
    BatteryCandidateResult,
    BatterySizingResults,
)
from celine.dt.apps.battery_sizing.simulation import simulate_battery_dispatch
from celine.dt.apps.battery_sizing.roi import (
    compute_candidate_metrics,
    simple_payback,
    npv,
)
from celine.dt.simulation.models import Scenario

TTL_PATH = Path(__file__).parent / "ontology.ttl"
JSONLD_PATH = Path(__file__).parent / "ontology.jsonld"

logger = logging.getLogger(__name__)


class BatterySizingApp(DTApp):
    key = "battery-sizing"
    version = "0.1.0"

    def __init__(self) -> None:
        self._cfg: dict[str, Any] = {}

    def configure(self, cfg: dict[str, Any]) -> None:
        self._cfg = dict(cfg or {})

    def ontology_ttl_files(self) -> list[str]:
        return [str(TTL_PATH)]

    def ontology_jsonld_files(self) -> list[str]:
        return [str(JSONLD_PATH)]

    def router(self) -> APIRouter:
        from celine.dt.apps.battery_sizing.api import router

        return router

    def create_scenario(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Merge defaults from YAML config then validate
        merged = dict(self._cfg)
        merged.update(payload or {})

        scenario = BatterySizingScenario.model_validate(merged)
        # serialize datetimes to ISO Z for core runner
        out = scenario.model_dump()
        out["start"] = (
            scenario.start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        out["end"] = (
            scenario.end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        return out

    def register_adapters(self) -> None:
        from celine.dt.apps.battery_sizing.adapter.register import register

        register()

    async def materialize(self, df: pd.DataFrame) -> pd.DataFrame:
        df["net_load_kw"] = df["load_kw"] - df["pv_kw"]
        return df

    async def fetch_inputs(
        self,
        adapter: DatasetAdapter,
        rec_id: str,
        start: datetime,
        end: datetime,
        granularity: str,
    ) -> pd.DataFrame:
        params = {
            "rec_id": rec_id,
            "start": start,
            "end": end,
            "granularity": granularity,
        }

        load_sql = """
        SELECT ts, value AS load_kw
        FROM load_timeseries
        WHERE rec_id = :rec_id
          AND ts BETWEEN :start AND :end
        """

        pv_sql = """
        SELECT ts, value AS pv_kw
        FROM pv_timeseries
        WHERE rec_id = :rec_id
          AND ts BETWEEN :start AND :end
        """

        load = await adapter.query(load_sql, params)
        pv = await adapter.query(pv_sql, params)

        return load.merge(pv, on="ts", how="left")

    async def run(
        self,
        payload: Scenario,
        df: pd.DataFrame,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = options or {}
        scenario = BatterySizingScenario.model_validate(
            {**(payload.payload_jsonld or {}), **options}
        )

        # Period length
        start = scenario.start
        end = scenario.end
        period_days = max(0.0001, (end - start).total_seconds() / 86400.0)

        # Baseline KPIs are computed in core endpoint; we recompute minimal baseline for deltas
        base_load = df["load_kw"].clip(lower=0)
        base_pv = df["pv_kw"].clip(lower=0)
        base_pv_to_load = pd.concat([base_pv, base_load], axis=1).min(axis=1)
        base_sc = (
            float(base_pv_to_load.sum() / base_pv.sum())
            if float(base_pv.sum()) > 0
            else 0.0
        )
        baseline = {
            "self_consumption_ratio": base_sc,
            "total_pv_kwh_equiv": float(base_pv.sum()),
            "total_load_kwh_equiv": float(base_load.sum()),
        }

        candidates: list[BatteryCandidateResult] = []
        for cap in scenario.capacity_kwh_candidates:
            power_kw = float(cap) / float(scenario.power_hours)
            sim_df = simulate_battery_dispatch(
                df,
                capacity_kwh=float(cap),
                power_kw=float(power_kw),
                round_trip_efficiency=float(scenario.round_trip_efficiency),
            )
            metrics = compute_candidate_metrics(df, sim_df, period_days=period_days)
            capex = (
                float(cap) * scenario.cost_per_kwh_eur
                + float(power_kw) * scenario.cost_per_kw_eur
                + scenario.installation_fixed_eur
            )
            payback = simple_payback(capex, metrics["annual_savings_eur_equiv"])
            cand = BatteryCandidateResult(
                capacity_kwh=float(cap),
                power_kw=float(power_kw),
                round_trip_efficiency=float(scenario.round_trip_efficiency),
                capex_eur=float(capex),
                annual_savings_eur_equiv=float(metrics["annual_savings_eur_equiv"]),
                simple_payback_years=payback,
                self_consumption_ratio_delta=float(
                    metrics["self_consumption_ratio_delta"]
                ),
            )
            # optional filter
            if scenario.max_simple_payback_years is not None and payback is not None:
                if payback > scenario.max_simple_payback_years:
                    continue
            candidates.append(cand)

        # rank: best NPV then savings; compute NPV for ranking
        ranked = []
        for c in candidates:
            c_npv = npv(
                c.capex_eur,
                c.annual_savings_eur_equiv,
                scenario.discount_rate,
                scenario.lifetime_years,
            )
            ranked.append((c_npv, c.annual_savings_eur_equiv, c))
        ranked.sort(key=lambda t: (t[0], t[1]), reverse=True)

        recommended = [t[2] for t in ranked[:3]]

        results = BatterySizingResults(
            baseline=baseline, recommended=recommended
        ).model_dump()

        # Output JSON-LD-ish payload; core will attach contexts
        return {
            "@type": "BatterySizingResult",
            "baseline": results["baseline"],
            "recommended": results["recommended"],
        }


def get_app() -> BatterySizingApp:
    return BatterySizingApp()
