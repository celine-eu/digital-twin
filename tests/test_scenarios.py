# tests/api/test_scenarios.py
import pytest
from celine.dt.api.scenarios import create_scenario
from celine.dt.api.schemas import ScenarioCreateRequest
from celine.dt.core.registry import AppRegistry


@pytest.mark.asyncio
async def test_create_scenario(db_session):
    registry = AppRegistry()
    registry._apps["dummy"] = type(
        "DtApp",
        (),
        {"create_scenario": lambda self, p: p},
    )()

    req = ScenarioCreateRequest(app_key="dummy", payload={"x": 1})
    res = await create_scenario(
        session=db_session,
        registry=registry,
        rec_id="rec-1",
        req=req,
    )

    assert res.rec_id == "rec-1"
