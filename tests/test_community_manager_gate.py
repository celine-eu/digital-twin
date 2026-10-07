# tests/test_community_manager_gate.py
"""
Who may read a community's manager fetchers (docs/specifications/community.md, REQ-151x).

The console reads them with its own service token, which no dataset-api row filter
narrows; ``EnergyCommunityDomain.check_fetch`` decides who may ask, before a statement
is rendered or sent.
"""
from __future__ import annotations

import json
import logging

import pytest
from celine.sdk.auth import JwtUser
from celine.sdk.auth.jwt import Organization
from fastapi.testclient import TestClient

from celine.dt.domains.energy_community.domain import ITEnergyCommunityDomain
from celine.dt.domains.energy_community.manager_fetchers import (
    MANAGER_FETCHER_IDS,
    MANAGER_SCOPE,
)

from tests.conftest import MockDatasetClient, build_app

COMMUNITY = "example-rec"
OTHER = "other-rec"
HEADERS = {"Authorization": "Bearer header.payload.signature"}
PERIOD = {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"}
MANAGER_FETCHER = "rec_population_summary"


def _person(scope: str = "", **groups: list[str]) -> JwtUser:
    """A user holding ``groups`` inside each organisation named by keyword."""
    sub = "0d6c4f9e-0000-4000-8000-000000000001"
    orgs = {alias.replace("_", "-"): {"groups": [f"/{g}" for g in gs]} for alias, gs in groups.items()}
    return JwtUser(
        sub=sub,
        claims={"sub": sub, "azp": "example-webapp", "email": "someone@example.org",
                "organization": orgs, "scope": scope},
        organizations=[Organization(alias=a, type="rec", groups=list(o["groups"]))
                       for a, o in orgs.items()],
    )


def _platform_admin() -> JwtUser:
    sub = "0d6c4f9e-0000-4000-8000-000000000002"
    return JwtUser(
        sub=sub,
        claims={"sub": sub, "azp": "example-webapp", "email": "admin@example.org",
                "realm_access": {"roles": ["platform-admin"]}},
    )


def _service(scope: str, client_id: str = "svc-community") -> JwtUser:
    sub = "0d6c4f9e-0000-4000-8000-0000000000aa"
    return JwtUser(
        sub=sub,
        claims={"sub": sub, "azp": client_id, "scope": scope,
                "preferred_username": f"service-account-{client_id}"},
    )


def _client(monkeypatch, caller: JwtUser):
    monkeypatch.setattr("celine.dt.api.context.parse_jwt_user", lambda token: caller)
    dataset = MockDatasetClient(rows=[])
    app = build_app(ITEnergyCommunityDomain(), client=dataset, authenticated=False)
    return TestClient(app, raise_server_exceptions=False), dataset


def _fetch(client, fetcher: str = MANAGER_FETCHER, community: str = COMMUNITY):
    return client.post(
        f"/communities/it/{community}/values/{fetcher}",
        json={"payload": PERIOD}, headers=HEADERS,
    )


def _reasons(caplog) -> list[str]:
    return [json.loads(r.getMessage()).get("reason") for r in caplog.records if r.name == "celine.audit"]


def test_the_console_fetchers_are_the_gated_ones() -> None:
    assert "rec_anti_gaming_flags_community" in MANAGER_FETCHER_IDS
    assert "rec_flexibility_chain_daily" in MANAGER_FETCHER_IDS
    assert "rec_self_consumption" not in MANAGER_FETCHER_IDS


class TestWhoReadsTheManagerFetchers:
    # @verifies REQ-1510
    @pytest.mark.parametrize(
        "caller",
        [
            _service(f"{MANAGER_SCOPE} digital-twin.values.read dataset.query"),
            _platform_admin(),
            _person(example_rec=["managers"]),
            _person(example_rec=["admins", "viewers"]),
        ],
        ids=["console service", "platform-admin", "manager", "admin"],
    )
    @pytest.mark.parametrize("fetcher", sorted(MANAGER_FETCHER_IDS))
    def test_who_runs_the_community_reads_every_manager_fetcher(self, monkeypatch, caller, fetcher):
        client, dataset = _client(monkeypatch, caller)
        payload = {**PERIOD, "device_id": "ex-00001"} if fetcher == "rec_device_points_ledger" else PERIOD
        resp = client.post(f"/communities/it/{COMMUNITY}/values/{fetcher}",
                           json={"payload": payload}, headers=HEADERS)
        assert resp.status_code == 200, resp.text
        assert dataset.calls == 1
        assert f"community_id = '{COMMUNITY}'" in dataset.last_sql

    # @verifies REQ-1510
    # @verifies REQ-1511
    @pytest.mark.parametrize(
        "caller, reason",
        [
            (_person(example_rec=["viewers"]), "community_not_managed"),
            (_person(other_rec=["managers", "admins"]), "community_not_managed"),
            (_person(), "community_not_managed"),
            # Organisation presence makes a person, whatever the scopes.
            (_person(MANAGER_SCOPE, other_rec=["managers"]), "community_not_managed"),
            (_service("digital-twin.values.read dataset.query", "svc-flexibility"),
             "manager_scope_missing"),
        ],
        ids=["member", "another community's manager", "no organisation",
             "person with the scope", "service without the scope"],
    )
    def test_anyone_else_is_refused_before_a_query(self, monkeypatch, caplog, caller, reason):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client, dataset = _client(monkeypatch, caller)
        resp = _fetch(client)
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["reason"] == reason
        assert dataset.calls == 0
        assert reason in _reasons(caplog)

    # @verifies REQ-1511
    def test_a_manager_of_two_communities_reads_each_under_its_own_name(self, monkeypatch):
        client, dataset = _client(monkeypatch, _person(example_rec=["managers"], other_rec=["viewers"]))
        assert _fetch(client, community=COMMUNITY).status_code == 200
        assert _fetch(client, community=OTHER).status_code == 403

    # @verifies REQ-1512
    @pytest.mark.parametrize(
        "caller",
        [_service("digital-twin.values.read dataset.query", "svc-flexibility"),
         _person(example_rec=["viewers"])],
        ids=["service without the scope", "member"],
    )
    def test_the_other_fetchers_are_not_gated(self, monkeypatch, caller):
        client, dataset = _client(monkeypatch, caller)
        resp = _fetch(client, fetcher="rec_self_consumption")
        assert resp.status_code == 200, resp.text
        assert dataset.calls == 1
