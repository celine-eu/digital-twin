# tests/test_grid_scoping.py
"""
Which network a grid read reaches, and who may name one (docs/specifications/grid.md).

celine-grid reads the twin with its own service token, which no dataset-api row filter
narrows, so the ``dso_id`` predicate is what keeps one operator's rows out of another's
answer; the gate in ``GridDomain.resolve_entity`` decides who may name the network.
"""
from __future__ import annotations

import json
import logging
import re

import pytest
from celine.sdk.auth import JwtUser
from celine.sdk.auth.jwt import Organization
from fastapi.testclient import TestClient

from celine.dt.contracts.entity import EntityInfo
from celine.dt.core.values.template import render_query
from celine.dt.domains.grid.domain import ITGridDomain

from tests.conftest import MockDatasetClient, build_app

GRID_TABLE = re.compile(r"FROM\s+ds_dev_gold\.(grid_\w+)", re.IGNORECASE)
SCOPE = "dso_id = {{ entity.id | sql_quote }}"
NETWORK = "example-dso"
HEADERS = {"Authorization": "Bearer header.payload.signature"}


def _specs():
    return ITGridDomain().get_value_specs()


def _params(spec) -> dict:
    """A value for every bind parameter, so the statement renders whole."""
    names = re.findall(r"(?<!:):([a-zA-Z_]\w*)", spec.query or "")
    return {n: "2026-01-01" for n in names}


# -- every read is narrowed to the network --------------------------------------


@pytest.mark.parametrize("spec", _specs(), ids=lambda s: s.id)
def test_every_grid_read_names_the_network(spec) -> None:
    """@verifies REQ-1312"""
    query = spec.query or ""
    reads = len(GRID_TABLE.findall(query))
    assert reads > 0, f"{spec.id} reads no grid table"
    assert query.count(SCOPE) == reads, (
        f"{spec.id}: {reads} grid read(s), {query.count(SCOPE)} restricted to the network"
    )


@pytest.mark.parametrize("spec", _specs(), ids=lambda s: s.id)
def test_the_network_stays_one_literal(spec) -> None:
    """@verifies REQ-1313"""
    hostile = "x' OR '1'='1"
    rendered = render_query(
        spec.query or "",
        entity=EntityInfo(id=hostile, domain_name="it-grid"),
        params={**_params(spec), "dates": ["2026-01-01"], "level": "tratta"},
    )
    assert "dso_id = 'x'' OR ''1''=''1'" in rendered
    assert "dso_id = 'x' OR" not in rendered


# -- who may name a network -----------------------------------------------------


def _person(*orgs: tuple[str, str], **claims) -> JwtUser:
    sub = "0d6c4f9e-0000-4000-8000-000000000001"
    return JwtUser(
        sub=sub,
        claims={"sub": sub, "azp": "example-webapp", "email": "someone@example.org", **claims},
        organizations=[Organization(alias=a, type=t) for a, t in orgs],
    )


def _service(scope: str) -> JwtUser:
    sub = "0d6c4f9e-0000-4000-8000-0000000000aa"
    return JwtUser(
        sub=sub,
        claims={"sub": sub, "azp": "svc-grid", "scope": scope,
                "preferred_username": "service-account-svc-grid"},
    )


def _client(monkeypatch, caller: JwtUser | None):
    if caller is not None:
        monkeypatch.setattr("celine.dt.api.context.parse_jwt_user", lambda token: caller)
    dataset = MockDatasetClient(rows=[])
    app = build_app(ITGridDomain(), client=dataset, authenticated=False)
    # the substations route queries through the registry, not a value fetcher
    app.state.infra.clients_registry.register("dataset_api", dataset)
    client = TestClient(app, raise_server_exceptions=False)
    return client, dataset


def _reasons(caplog) -> list[str]:
    return [json.loads(r.getMessage()).get("reason") for r in caplog.records if r.name == "celine.audit"]


class TestWhoMayNameANetwork:
    # @verifies REQ-1320
    def test_a_member_of_the_dso_reads_its_network(self, monkeypatch):
        client, dataset = _client(monkeypatch, _person((NETWORK, "dso")))
        resp = client.get(f"/grid/{NETWORK}/values/filters", headers=HEADERS)
        assert resp.status_code == 200
        assert dataset.calls == 1
        assert f"dso_id = '{NETWORK}'" in dataset.last_sql

    # @verifies REQ-1320
    # @verifies REQ-1323
    # @verifies REQ-1324
    @pytest.mark.parametrize(
        "caller",
        [
            _person(("other-dso", "dso")),
            _person((NETWORK, "rec")),
            _person(),
            _person(realm_access={"roles": ["platform-admin"]}),
        ],
        ids=["another-dso", "same-alias-not-a-dso", "no-organisation", "platform-admin"],
    )
    def test_anyone_else_is_refused_before_a_query(self, monkeypatch, caplog, caller):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client, dataset = _client(monkeypatch, caller)
        resp = client.get(f"/grid/{NETWORK}/values/filters", headers=HEADERS)
        assert resp.status_code == 403
        assert dataset.calls == 0
        assert "network_not_owned" in _reasons(caplog)

    # @verifies REQ-1321
    @pytest.mark.parametrize("scope", ["grid.read", "grid.admin dataset.query"])
    def test_a_service_with_a_grid_scope_reads_any_network(self, monkeypatch, scope):
        client, dataset = _client(monkeypatch, _service(scope))
        resp = client.get(f"/grid/{NETWORK}/values/filters", headers=HEADERS)
        assert resp.status_code == 200
        assert f"dso_id = '{NETWORK}'" in dataset.last_sql

    # @verifies REQ-1321
    def test_a_service_without_a_grid_scope_is_refused(self, monkeypatch, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client, dataset = _client(monkeypatch, _service("digital-twin.values.read dataset.query"))
        resp = client.get(f"/grid/{NETWORK}/values/filters", headers=HEADERS)
        assert resp.status_code == 403
        assert dataset.calls == 0
        assert "grid_scope_missing" in _reasons(caplog)

    # @verifies REQ-1322
    def test_a_grid_scope_does_not_widen_a_person(self, monkeypatch, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        caller = _person((NETWORK, "dso"), scope="grid.admin")
        client, dataset = _client(monkeypatch, caller)
        resp = client.get("/grid/other-dso/values/filters", headers=HEADERS)
        assert resp.status_code == 403
        assert dataset.calls == 0
        assert "network_not_owned" in _reasons(caplog)

    # @verifies REQ-1325
    @pytest.mark.parametrize(
        "method, path",
        [("GET", "info"), ("GET", "values/filters"), ("POST", "values/risks"),
         ("GET", "substations/map")],
    )
    def test_the_gate_holds_on_every_route(self, monkeypatch, caplog, method, path):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client, dataset = _client(monkeypatch, _person((NETWORK, "dso")))
        resp = client.request(method, f"/grid/other-dso/{path}", headers=HEADERS,
                              json={"dates": ["2026-01-01"]} if method == "POST" else None)
        assert resp.status_code == 403
        assert dataset.calls == 0
        assert "network_not_owned" in _reasons(caplog)

    def test_no_token_is_401(self, monkeypatch):
        client, dataset = _client(monkeypatch, None)
        resp = client.get(f"/grid/{NETWORK}/values/filters")
        assert resp.status_code == 401
        assert dataset.calls == 0


class TestRoutes:
    # @verifies REQ-1314
    def test_the_substation_layer_is_the_networks(self, monkeypatch):
        client, dataset = _client(monkeypatch, _person((NETWORK, "dso")))
        resp = client.get(f"/grid/{NETWORK}/substations/map", headers=HEADERS)
        assert resp.status_code == 200
        assert f"dso_id = '{NETWORK}'" in dataset.last_sql

    # @verifies REQ-1330
    @pytest.mark.parametrize(
        "path",
        ["wind/map", "wind/bosco", "wind/alert-distribution", "wind/trend",
         "heat/map", "heat/alert-distribution", "heat/trend"],
    )
    def test_the_legacy_wind_and_heat_routes_are_gone(self, monkeypatch, path):
        client, dataset = _client(monkeypatch, _person((NETWORK, "dso")))
        resp = client.get(f"/grid/{NETWORK}/{path}", headers=HEADERS)
        assert resp.status_code == 404
        assert dataset.calls == 0
