# tests/e2e/test_community_managers.py
"""
A community's manager fetchers through the running services (REQ-1503, REQ-1513).

Runs against a live stack whose warehouse holds REC rows of two communities, and is
skipped unless it is told where everything is. Nothing here names a real community:

    COMMUNITY_E2E_DT_URL           the Digital Twin, e.g. http://127.0.0.1:8002
    COMMUNITY_E2E_COMMUNITY        a community whose warehouse rows exist
    COMMUNITY_E2E_OTHER            a second community with rows of its own
    COMMUNITY_E2E_SERVICE_TOKEN    the console's client-credentials token (svc-community)
    COMMUNITY_E2E_MANAGER_TOKEN    a `managers` user of COMMUNITY_E2E_COMMUNITY
    COMMUNITY_E2E_VIEWER_TOKEN     a `viewers` user of COMMUNITY_E2E_COMMUNITY
    COMMUNITY_E2E_OTHER_MANAGER_TOKEN  a `managers` user of COMMUNITY_E2E_OTHER only

and, optionally (its test skips without it):

    COMMUNITY_E2E_UNSCOPED_SERVICE_TOKEN  a service that reads the twin but does not hold
                                          `digital-twin.community.manage` (svc-flexibility)
"""
from __future__ import annotations

import os

import httpx
import pytest

ENV = ("COMMUNITY_E2E_DT_URL", "COMMUNITY_E2E_COMMUNITY", "COMMUNITY_E2E_OTHER",
       "COMMUNITY_E2E_SERVICE_TOKEN", "COMMUNITY_E2E_MANAGER_TOKEN",
       "COMMUNITY_E2E_VIEWER_TOKEN", "COMMUNITY_E2E_OTHER_MANAGER_TOKEN")

pytestmark = pytest.mark.skipif(
    any(not os.environ.get(k) for k in ENV), reason="needs a live stack: " + ", ".join(ENV)
)

PERIOD = {"start": "2000-01-01T00:00:00Z", "end": "2100-01-01T00:00:00Z"}

#: The manager fetchers that answer one row per device.
DEVICE_FETCHERS = ("rec_meters_missing_intervals", "rec_device_streaks",
                   "rec_points_leaderboard_community", "rec_flexibility_chain_daily",
                   "rec_anti_gaming_flags_community")


def _env(key: str) -> str:
    return os.environ[key]


def _fetch(community: str, fetcher: str, token: str) -> httpx.Response:
    return httpx.post(
        f"{_env('COMMUNITY_E2E_DT_URL')}/communities/it/{community}/values/{fetcher}",
        json={"payload": PERIOD},
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )


def _devices(community: str, token: str) -> set[str]:
    devices: set[str] = set()
    for fetcher in DEVICE_FETCHERS:
        resp = _fetch(community, fetcher, token)
        assert resp.status_code == 200, f"{fetcher}: {resp.status_code} {resp.text}"
        devices |= {r["device_id"] for r in resp.json()["items"] if r.get("device_id")}
    return devices


# @verifies REQ-1503
def test_the_console_reads_one_community_per_entity():
    token = _env("COMMUNITY_E2E_SERVICE_TOKEN")
    own = _devices(_env("COMMUNITY_E2E_COMMUNITY"), token)
    other = _devices(_env("COMMUNITY_E2E_OTHER"), token)
    assert own, "the community has no device rows: the warehouse holds no REC data"
    assert other, "the second community has no device rows"
    assert not own & other


# @verifies REQ-1513
def test_the_community_manager_and_the_console_are_served():
    community = _env("COMMUNITY_E2E_COMMUNITY")
    for key in ("COMMUNITY_E2E_MANAGER_TOKEN", "COMMUNITY_E2E_SERVICE_TOKEN"):
        resp = _fetch(community, "rec_population_summary", _env(key))
        assert resp.status_code == 200, f"{key}: {resp.text}"


# @verifies REQ-1513
@pytest.mark.parametrize("key", ["COMMUNITY_E2E_VIEWER_TOKEN", "COMMUNITY_E2E_OTHER_MANAGER_TOKEN"])
def test_a_member_and_another_communitys_manager_are_refused(key):
    resp = _fetch(_env("COMMUNITY_E2E_COMMUNITY"), "rec_population_summary", _env(key))
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["reason"] == "community_not_managed"


# @verifies REQ-1510
@pytest.mark.skipif(not os.environ.get("COMMUNITY_E2E_UNSCOPED_SERVICE_TOKEN"),
                    reason="needs COMMUNITY_E2E_UNSCOPED_SERVICE_TOKEN")
def test_a_service_without_the_manager_scope_is_refused():
    resp = _fetch(_env("COMMUNITY_E2E_COMMUNITY"), "rec_population_summary",
                  _env("COMMUNITY_E2E_UNSCOPED_SERVICE_TOKEN"))
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["reason"] == "manager_scope_missing"
