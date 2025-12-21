from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class MaterializeResponse(BaseModel):
    rec_id: str
    rows_inserted: int


class KPIResponse(BaseModel):
    rec_id: str
    start: datetime
    end: datetime
    kpis: dict = Field(default_factory=dict)


class ScenarioCreateRequest(BaseModel):
    app_key: str
    payload: dict


class ScenarioCreateResponse(BaseModel):
    scenario_id: str
    app_key: str
    rec_id: str
    payload: dict


class RunCreateRequest(BaseModel):
    model: str = "default"
    # allow overriding app config etc.
    options: dict = Field(default_factory=dict)


class RunCreateResponse(BaseModel):
    run_id: str
    status: str


class RunResultResponse(BaseModel):
    run_id: str
    results: dict
