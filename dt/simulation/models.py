from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, Column, JSON


class EnergyCommunity(SQLModel, table=True):
    rec_id: str = Field(primary_key=True, index=True)
    name: str
    metadata_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MaterializedTimeSeries(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    rec_id: str = Field(index=True)
    ts: datetime = Field(index=True)

    load_kw: float
    pv_kw: float

    import_price_eur_per_kwh: float = 0.0
    export_price_eur_per_kwh: float = 0.0

    quality_flag: str = "ok"


class Scenario(SQLModel, table=True):
    scenario_id: str = Field(primary_key=True, index=True)
    rec_id: str = Field(index=True)
    app_key: str = Field(index=True)
    payload_jsonld: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Run(SQLModel, table=True):
    run_id: str = Field(primary_key=True, index=True)
    scenario_id: str = Field(index=True)
    model: str
    status: str = "created"  # created|running|success|failed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    provenance_json: dict = Field(default_factory=dict, sa_column=Column(JSON))


class RunResult(SQLModel, table=True):
    run_id: str = Field(primary_key=True)
    results_jsonld: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
