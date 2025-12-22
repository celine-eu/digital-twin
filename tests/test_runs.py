# tests/api/test_runs.py
import pytest
import pandas as pd
from celine.dt.api.runs import create_run
from celine.dt.api.schemas import RunCreateRequest
from celine.dt.db.models import Scenario


class FakeApp:
    key = "x"
    version = "0"

    async def fetch_inputs(self, *a, **k):
        return pd.DataFrame(
            {
                "load_kw": [1],
                "pv_kw": [1],
                "import_price_eur_per_kwh": [0.2],
                "export_price_eur_per_kwh": [0.1],
            }
        )

    async def materialize(self, df):
        return df

    async def run(self, payload, df, options):
        return {"ok": True}


@pytest.mark.asyncio
async def test_run_success(db_session, monkeypatch):
    scenario = Scenario(
        scenario_id="s1",
        rec_id="r1",
        app_key="x",
        payload_jsonld={
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-01-02T00:00:00Z",
        },
    )
    db_session.add(scenario)
    await db_session.commit()

    class FakeApp:
        key = "x"
        version = "0"

        async def fetch_inputs(self, *a, **k):
            return pd.DataFrame(
                {
                    "load_kw": [1],
                    "pv_kw": [1],
                    "import_price_eur_per_kwh": [0.2],
                    "export_price_eur_per_kwh": [0.1],
                }
            )

        async def materialize(self, df):
            return df

        async def run(self, payload, df, options):
            return {"ok": True}

    registry = type("R", (), {"apps": {"x": FakeApp()}})()

    monkeypatch.setattr(
        "celine.dt.api.runs.get_dataset_adapter_for_app",
        lambda *_: None,
    )

    # IMPORTANT: new session for run
    res = await create_run(
        session=db_session,
        registry=registry,
        jsonld_context_files=[],
        scenario_id="s1",
        req=RunCreateRequest(),
    )

    assert res.status == "success"
