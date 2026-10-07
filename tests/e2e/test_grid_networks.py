# tests/e2e/test_grid_networks.py
"""
Every grid read answers one operator's rows, through the running services (REQ-1326).

Runs against a live stack whose warehouse holds grid rows of one operator only, and is
skipped unless it is told where everything is. Nothing here names a real network:

    GRID_E2E_DT_URL          the Digital Twin, e.g. http://127.0.0.1:8002
    GRID_E2E_NETWORK         the operator whose rows the warehouse holds
    GRID_E2E_EMPTY_NETWORK   another dso organisation's alias, with no rows
    GRID_E2E_SERVICE_TOKEN   a client-credentials token holding a grid.* scope
    GRID_E2E_OWN_TOKEN       a user of GRID_E2E_NETWORK's organisation
    GRID_E2E_OTHER_TOKEN     a user of GRID_E2E_EMPTY_NETWORK's organisation only
"""
from __future__ import annotations

import os

import httpx
import pytest

ENV = ("GRID_E2E_DT_URL", "GRID_E2E_NETWORK", "GRID_E2E_EMPTY_NETWORK",
       "GRID_E2E_SERVICE_TOKEN", "GRID_E2E_OWN_TOKEN", "GRID_E2E_OTHER_TOKEN")

pytestmark = pytest.mark.skipif(
    any(not os.environ.get(k) for k in ENV), reason="needs a live stack: " + ", ".join(ENV)
)


def _env(key: str) -> str:
    return os.environ[key]


def _fetch(network: str, fetcher: str, payload: dict, token: str) -> httpx.Response:
    return httpx.post(
        f"{_env('GRID_E2E_DT_URL')}/grid/{network}/values/{fetcher}",
        json={"payload": payload},
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )


@pytest.fixture(scope="module")
def latest_date() -> str:
    """The latest day the warehouse holds for the network, from its own trendline."""
    resp = _fetch(_env("GRID_E2E_NETWORK"), "trendline",
                  {"date_from": "2000-01-01", "date_to": "2100-01-01"},
                  _env("GRID_E2E_SERVICE_TOKEN"))
    assert resp.status_code == 200, resp.text
    dates = sorted({r["date"] for r in resp.json()["items"]})
    assert dates, "the network has no trendline rows: the warehouse holds no grid data"
    return dates[-1]


def _fetchers(day: str) -> dict[str, dict]:
    return {
        "filters": {},
        "tile_index": {},
        "shapes": {},
        "risks": {"dates": [day]},
        "risk_km": {"dates": [day]},
        "tree_strike_spans": {},
        "risks_8h": {"dates": [day]},
        "trendline": {"date_from": day, "date_to": day},
    }


def _count(resp: httpx.Response, fetcher: str) -> int:
    items = resp.json()["items"]
    if fetcher == "filters":
        # one aggregation row; empty arrays and a NULL extent when nothing matched
        return sum(len(v or []) for k, v in items[0].items() if isinstance(v, list))
    return len(items)


# @verifies REQ-1326
def test_the_grid_service_reads_its_network_and_nothing_of_another(latest_date):
    token = _env("GRID_E2E_SERVICE_TOKEN")
    for fetcher, payload in _fetchers(latest_date).items():
        own = _fetch(_env("GRID_E2E_NETWORK"), fetcher, payload, token)
        empty = _fetch(_env("GRID_E2E_EMPTY_NETWORK"), fetcher, payload, token)
        assert own.status_code == 200, (fetcher, own.text)
        assert empty.status_code == 200, (fetcher, empty.text)
        if fetcher not in ("risks", "risks_8h"):  # a calm day may have no WARNING/ALERT
            assert _count(own, fetcher) > 0, f"{fetcher}: no rows for the network"
        assert _count(empty, fetcher) == 0, f"{fetcher}: rows answered for another network"


# @verifies REQ-1326
def test_a_user_reads_their_network_and_is_refused_another():
    own = _fetch(_env("GRID_E2E_NETWORK"), "filters", {}, _env("GRID_E2E_OWN_TOKEN"))
    assert own.status_code == 200, own.text
    crossed = _fetch(_env("GRID_E2E_NETWORK"), "filters", {}, _env("GRID_E2E_OTHER_TOKEN"))
    assert crossed.status_code == 403, crossed.text


# @verifies REQ-1326
def test_the_substation_layer_is_the_networks():
    url = f"{_env('GRID_E2E_DT_URL')}/grid/{{}}/substations/map"
    headers = {"Authorization": f"Bearer {_env('GRID_E2E_SERVICE_TOKEN')}"}
    own = httpx.get(url.format(_env("GRID_E2E_NETWORK")), headers=headers, timeout=120)
    empty = httpx.get(url.format(_env("GRID_E2E_EMPTY_NETWORK")), headers=headers, timeout=120)
    assert own.status_code == 200 and own.json()["features"], own.text
    assert empty.status_code == 200 and empty.json()["features"] == [], empty.text
