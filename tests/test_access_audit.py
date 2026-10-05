# tests/test_access_audit.py
"""
The access audit (who read which twin, entity and value) and API documentation
exposure.

The app is the conftest one built with ``authenticated=False``, so ``require_user``
runs; the token check itself is replaced by a stub of ``parse_jwt_user``, the one
place the real service verifies a JWT. Records are read from the ``celine.audit``
logger with ``caplog``.
"""
from __future__ import annotations

import json
import logging

import pytest
from celine.sdk.auth import JwtUser
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from celine.dt.api.audit import note_reason
from celine.dt.contracts.entity import EntityInfo

from tests.conftest import MockDatasetClient, build_app
from tests.sample_domain.domain import SampleCommunityDomain, StrictCommunityDomain

SUB = "0d6c4f9e-0000-4000-8000-000000000001"
EMAIL = "member@example.org"
NAME = "Example Member"
USERNAME = "example.member"
TOKEN = "Bearer header.payload.signature"


def _user() -> JwtUser:
    claims = {
        "sub": SUB,
        "azp": "example-webapp",
        "email": EMAIL,
        "name": NAME,
        "preferred_username": USERNAME,
    }
    return JwtUser(
        sub=SUB, email=EMAIL, name=NAME, preferred_username=USERNAME, claims=claims
    )


@pytest.fixture
def verified(monkeypatch):
    """Every presented token verifies as ``_user()``."""
    monkeypatch.setattr("celine.dt.api.context.parse_jwt_user", lambda token: _user())


@pytest.fixture
def refused(monkeypatch):
    """Every presented token fails verification, as an expired one does."""

    def _refuse(token):
        raise ValueError(f"Signature has expired for {EMAIL}")

    monkeypatch.setattr("celine.dt.api.context.parse_jwt_user", _refuse)


def _records(caplog) -> list[dict]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "celine.audit"]


def _assert_no_personal_data(caplog) -> None:
    for record in caplog.records:
        if record.name != "celine.audit":
            continue
        line = record.getMessage()
        for value in (EMAIL, NAME, USERNAME, "header.payload.signature"):
            assert value not in line


def _client(*domains, rows=None) -> TestClient:
    return TestClient(
        build_app(*domains, client=MockDatasetClient(rows or []), authenticated=False)
    )


# -- reads ----------------------------------------------------------------------


class TestAccessRecorded:
    # @verifies REQ-1080
    def test_read_records_caller_route_and_entity(self, verified, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        resp = _client(SampleCommunityDomain()).get(
            "/communities/rec-1/info",
            headers={"Authorization": TOKEN, "X-Request-ID": "req-1"},
        )
        assert resp.status_code == 200

        [record] = _records(caplog)
        assert record["event"] == "access"
        assert record["outcome"] == "allowed"
        assert record["action"] == "twin.read"
        assert record["sub"] == SUB
        assert record["client_id"] == "example-webapp"
        assert record["method"] == "GET"
        assert record["route"] == "/communities/{community_id}/info"
        assert record["resource"] == "test-community/rec-1"
        assert record["request_id"] == "req-1"
        _assert_no_personal_data(caplog)

    # @verifies REQ-1080
    def test_values_read_names_the_fetcher(self, verified, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        resp = _client(SampleCommunityDomain(), rows=[{"v": 1}]).get(
            "/communities/rec-1/values/consumption?since=2026-01-01",
            headers={"Authorization": TOKEN},
        )
        assert resp.status_code == 200

        [record] = _records(caplog)
        assert record["outcome"] == "allowed"
        assert record["route"] == "/communities/{community_id}/values/{fetcher_id}"
        assert record["resource"] == "test-community/rec-1/consumption"
        assert "2026-01-01" not in json.dumps(record)

    # @verifies REQ-1080
    def test_domain_route_is_recorded(self, verified, caplog):
        """A route from a domain's own `routes/` package sits in the same entity scope.

        The sample route depends on `get_ctx`, not `get_ctx_auth`; the caller it
        verified is recorded all the same.
        """
        caplog.set_level(logging.INFO, logger="celine.audit")
        resp = _client(SampleCommunityDomain()).get(
            "/communities/rec-1/extra/echo", headers={"Authorization": TOKEN}
        )
        assert resp.status_code == 200
        [record] = _records(caplog)
        assert record["route"] == "/communities/{community_id}/extra/echo"
        assert record["sub"] == SUB

    # @verifies REQ-1080
    def test_error_is_recorded_once_as_error(self, verified, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        resp = _client(SampleCommunityDomain()).get(
            "/communities/rec-1/values/unknown", headers={"Authorization": TOKEN}
        )
        assert resp.status_code == 404

        [record] = _records(caplog)
        assert record["event"] == "access"
        assert record["outcome"] == "error"
        assert record["reason"] == "http 404"
        assert record["sub"] == SUB

    # @verifies REQ-1080
    def test_discovery_is_not_recorded(self, verified, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client = _client(SampleCommunityDomain())
        assert client.get("/health").status_code == 200
        assert client.get("/domains").status_code == 200
        assert _records(caplog) == []


# -- refusals -------------------------------------------------------------------


class TestDenialRecorded:
    # @verifies REQ-1041
    # @verifies REQ-1081
    def test_token_failing_verification_is_401_and_denied(self, refused, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        resp = _client(SampleCommunityDomain()).get(
            "/communities/rec-1/info", headers={"Authorization": TOKEN}
        )
        assert resp.status_code == 401
        assert EMAIL not in resp.text

        [record] = _records(caplog)
        assert record["event"] == "denied"
        assert record["outcome"] == "denied"
        assert record["reason"] == "invalid_token"
        assert record["sub"] is None
        assert record["route"] == "/communities/{community_id}/info"
        assert record["resource"] == "test-community/rec-1"
        _assert_no_personal_data(caplog)

    # @verifies REQ-1081
    def test_audit_denial_is_a_warning(self, refused, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        _client(SampleCommunityDomain()).get(
            "/communities/rec-1/info", headers={"Authorization": TOKEN}
        )
        [record] = [r for r in caplog.records if r.name == "celine.audit"]
        assert record.levelno == logging.WARNING

    # @verifies REQ-1081
    def test_missing_token_is_denied(self, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        resp = _client(SampleCommunityDomain()).get("/communities/rec-1/values")
        assert resp.status_code == 401

        [record] = _records(caplog)
        assert record["event"] == "denied"
        assert record["reason"] == "no_token"
        assert record["sub"] is None

    # @verifies REQ-1081
    def test_rejected_entity_is_denied_with_the_caller(self, verified, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        resp = _client(StrictCommunityDomain()).get(
            "/strict/unknown-id/info", headers={"Authorization": TOKEN}
        )
        assert resp.status_code == 404

        [record] = _records(caplog)
        assert record["event"] == "denied"
        assert record["reason"] == "entity_rejected"
        assert record["sub"] == SUB
        assert record["client_id"] == "example-webapp"
        assert record["resource"] == "strict-community/unknown-id"
        _assert_no_personal_data(caplog)

    # @verifies REQ-1082
    def test_email_shaped_entity_id_is_pseudonymised(self, verified, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        _client(SampleCommunityDomain()).get(
            f"/communities/{EMAIL}/info", headers={"Authorization": TOKEN}
        )
        [record] = _records(caplog)
        assert record["resource"].startswith("h:")
        _assert_no_personal_data(caplog)


class GatedCommunityDomain(SampleCommunityDomain):
    """Entity resolution answering each way a gate can end a request."""

    name = "gated-community"
    route_prefix = "/gated"

    async def resolve_entity(self, entity_id: str, request: Request) -> EntityInfo | None:
        if entity_id == "closed":
            raise HTTPException(403, "refused")
        if entity_id == "hidden":
            note_reason(request, "not_owner")
            raise HTTPException(404, "not found")
        if entity_id == "noted-forbidden":
            note_reason(request, "not_member")
            raise HTTPException(403, "refused")
        if entity_id == "broken":
            note_reason(request, "not_owner")
            raise RuntimeError("boom")
        return await super().resolve_entity(entity_id, request)


class TestEveryOutcomeOfTheEntityScope:
    """The record each way a request can end; the cases the reason codes do not cover."""

    # @verifies REQ-1080
    # @verifies REQ-1081
    @pytest.mark.parametrize(
        ("entity", "status", "event", "outcome", "reason"),
        [
            ("rec-1", 200, "access", "allowed", None),
            ("closed", 403, "denied", "denied", "http 403"),
            ("hidden", 404, "denied", "denied", "not_owner"),
            ("noted-forbidden", 403, "denied", "denied", "not_member"),
            ("broken", 500, "access", "error", "RuntimeError"),
        ],
    )
    def test_one_record_per_outcome(
        self, verified, caplog, entity, status, event, outcome, reason
    ):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client = TestClient(
            build_app(
                GatedCommunityDomain(), client=MockDatasetClient([]), authenticated=False
            ),
            raise_server_exceptions=False,
        )
        resp = client.get(f"/gated/{entity}/info", headers={"Authorization": TOKEN})
        assert resp.status_code == status

        [record] = _records(caplog)
        assert (record["event"], record["outcome"], record["reason"]) == (
            event,
            outcome,
            reason,
        )
        assert record["action"] == "twin.read"
        assert record["sub"] == SUB
        assert record["route"] == "/gated/{community_id}/info"
        assert record["resource"] == f"gated-community/{entity}"
        _assert_no_personal_data(caplog)


# -- API documentation ------------------------------------------------------------

_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


def _create_app(monkeypatch, **env: str):
    """``create_app`` under ``env``, with the posture check (REQ-106x) stubbed out."""
    for name in ("CELINE_ENV", "ENVIRONMENT", "APP_ENV", "ENV", "CELINE_PUBLIC_DOCS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("celine.dt.main.check_posture", lambda settings: None)
    from celine.dt.main import create_app

    return TestClient(create_app())


class TestApiDocs:
    # @verifies REQ-1053
    @pytest.mark.parametrize("env", [{}, {"CELINE_ENV": "prod"}, {"CELINE_PUBLIC_DOCS": "no"}])
    def test_hidden_outside_dev(self, monkeypatch, env):
        client = _create_app(monkeypatch, **env)
        for path in _DOC_PATHS:
            assert client.get(path).status_code == 404, path

    # @verifies REQ-1053
    def test_served_in_dev(self, monkeypatch):
        client = _create_app(monkeypatch, CELINE_ENV="dev")
        for path in _DOC_PATHS:
            assert client.get(path).status_code == 200, path
        assert "/health" in client.get("/openapi.json").json()["paths"]

    # @verifies REQ-1053
    def test_served_when_opted_in(self, monkeypatch):
        client = _create_app(monkeypatch, CELINE_ENV="prod", CELINE_PUBLIC_DOCS="true")
        for path in _DOC_PATHS:
            assert client.get(path).status_code == 200, path
