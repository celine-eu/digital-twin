# tests/test_participant_scoping.py
"""
A participant twin is the caller's own (REQ-1400 - REQ-1404, REQ-1116).

The app is the conftest one built with ``authenticated=False``, so ``require_user``
runs; the token check is replaced by a stub of ``parse_jwt_user`` and the REC registry
by an in-memory double answering ``get_me`` and ``get_my_assets``. Records are read
from the ``celine.audit`` logger with ``caplog``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from celine.sdk.auth import JwtUser
from fastapi.testclient import TestClient

from celine.dt.domains.participant.domain import ITParticipantDomain
from tests.conftest import MockDatasetClient, build_app

SUB = "0d6c4f9e-0000-4000-8000-000000000001"
OTHER = "0d6c4f9e-0000-4000-8000-000000000002"
OWN_DEVICE = "ex-meter-00001"
FOREIGN_DEVICE = "ex-meter-00002"
TOKEN = "Bearer header.payload.signature"
HEADERS = {"Authorization": TOKEN}


@dataclass
class _Keyed:
    """A member or community summary; a dataclass so `/info` can serialise it."""

    key: str
    name: str


class FakeRegistry:
    """The two ``/user`` answers the participant domain asks for, and a call log."""

    def __init__(
        self,
        sub: str = SUB,
        devices=(OWN_DEVICE,),
        assets_fail: bool = False,
        member: bool = True,
    ):
        self.sub = sub
        self.member = member
        self.devices = list(devices)
        self.assets_fail = assets_fail
        self.calls: list[str] = []

    async def get_me(self, token: str):
        self.calls.append("get_me")
        profile = SimpleNamespace(sub=self.sub, email="member@example.org")
        if not self.member:
            return SimpleNamespace(profile=profile, membership=None)
        return SimpleNamespace(
            profile=profile,
            membership=SimpleNamespace(
                member=_Keyed(key="ex-00001", name="Example Member"),
                community=_Keyed(key="example-rec", name="Example REC"),
            ),
        )

    async def get_my_assets(self, token: str):
        self.calls.append("get_my_assets")
        if self.assets_fail:
            raise RuntimeError("registry unavailable")
        return SimpleNamespace(
            items=[SimpleNamespace(sensor_id=d) for d in self.devices]
            + [SimpleNamespace(sensor_id=None)]  # a PV plant: no meter
        )


def _member(**extra_claims) -> JwtUser:
    claims = {"sub": SUB, "azp": "example-webapp", **extra_claims}
    return JwtUser(sub=SUB, claims=claims)


@pytest.fixture
def as_member(monkeypatch):
    monkeypatch.setattr("celine.dt.api.context.parse_jwt_user", lambda token: _member())


def _setup(registry: FakeRegistry | None = None, rows=None):
    domain = ITParticipantDomain()
    registry = registry or FakeRegistry()
    domain._registry_client = registry
    dataset = MockDatasetClient(rows if rows is not None else [{"device_id": OWN_DEVICE}])
    client = TestClient(
        build_app(domain, client=dataset, authenticated=False),
        raise_server_exceptions=False,
    )
    return client, registry, dataset


def _records(caplog) -> list[dict]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "celine.audit"]


# -- the caller's own participant -----------------------------------------------


class TestOwnParticipant:
    # @verifies REQ-1401
    # @verifies REQ-1402
    def test_own_participant_and_own_device_are_served(self, as_member, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client, registry, dataset = _setup()

        resp = client.get(
            f"/participants/{SUB}/values/meters_data?device_id={OWN_DEVICE}",
            headers=HEADERS,
        )

        assert resp.status_code == 200
        assert resp.json()["items"] == [{"device_id": OWN_DEVICE}]
        assert dataset.calls == 1
        assert registry.calls == ["get_me", "get_my_assets"]
        [record] = _records(caplog)
        assert record["outcome"] == "allowed"
        assert record["sub"] == SUB

    # @verifies REQ-1401
    def test_own_participant_info_is_served(self, as_member):
        client, registry, _ = _setup()
        resp = client.get(f"/participants/{SUB}/info", headers=HEADERS)
        assert resp.status_code == 200
        assert registry.calls == ["get_me"]

    # @verifies REQ-1401
    def test_own_participant_without_membership_is_not_found(self, as_member, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client, _, dataset = _setup(FakeRegistry(member=False))
        resp = client.get(f"/participants/{SUB}/info", headers=HEADERS)
        assert resp.status_code == 404
        assert dataset.calls == 0
        [record] = _records(caplog)
        assert record["reason"] == "entity_rejected"

    # @verifies REQ-1402
    def test_fetch_naming_no_device_does_not_ask_for_assets(self, as_member):
        client, registry, dataset = _setup(rows=[])
        resp = client.get(f"/participants/{SUB}/values/total_meters_forecast", headers=HEADERS)
        assert resp.status_code == 200
        assert "get_my_assets" not in registry.calls
        assert dataset.calls == 1


# -- another participant --------------------------------------------------------


class TestOtherParticipant:
    # @verifies REQ-1400
    @pytest.mark.parametrize(
        "path",
        [
            f"/participants/{OTHER}/profile",
            f"/participants/{OTHER}/assets",
            f"/participants/{OTHER}/values/total_meters_forecast",
            f"/participants/{OTHER}/values/meters_data?device_id={OWN_DEVICE}",
            f"/participants/{OTHER}/info",
        ],
    )
    def test_other_participant_is_refused_and_audited(self, as_member, caplog, path):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client, registry, dataset = _setup()

        resp = client.get(path, headers=HEADERS)

        assert resp.status_code == 403
        assert registry.calls == []
        assert dataset.calls == 0
        [record] = _records(caplog)
        assert record["event"] == "denied"
        assert record["outcome"] == "denied"
        assert record["reason"] == "participant_not_caller"
        assert record["sub"] == SUB
        assert record["resource"].startswith(f"it-participant/{OTHER}")

    # @verifies REQ-1403
    @pytest.mark.parametrize(
        "claims",
        [
            {"realm_access": {"roles": ["platform-admin"]}},
            {"preferred_username": "service-account-example-svc"},
            {"organization": {"example-rec": {"groups": ["/admins", "/managers"]}}},
        ],
        ids=["platform-admin", "service-account", "organization-admin"],
    )
    def test_no_role_widens_the_scope(self, monkeypatch, caplog, claims):
        monkeypatch.setattr("celine.dt.api.context.parse_jwt_user", lambda token: _member(**claims))
        caplog.set_level(logging.INFO, logger="celine.audit")
        client, _, dataset = _setup()

        resp = client.get(
            f"/participants/{OTHER}/values/meters_data?device_id={FOREIGN_DEVICE}",
            headers=HEADERS,
        )

        assert resp.status_code == 403
        assert dataset.calls == 0
        [record] = _records(caplog)
        assert record["reason"] == "participant_not_caller"


# -- a device the caller does not own -------------------------------------------


class TestForeignDevice:
    # @verifies REQ-1402
    # @verifies REQ-1116
    def test_foreign_device_get_is_refused_and_audited(self, as_member, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client, _, dataset = _setup()

        resp = client.get(
            f"/participants/{SUB}/values/meters_data?device_id={FOREIGN_DEVICE}",
            headers=HEADERS,
        )

        assert resp.status_code == 403
        assert resp.json()["detail"]["reason"] == "device_not_owned"
        assert dataset.calls == 0
        [record] = _records(caplog)
        assert record["event"] == "denied"
        assert record["reason"] == "device_not_owned"
        assert record["sub"] == SUB
        assert record["resource"] == f"it-participant/{SUB}/meters_data"
        assert FOREIGN_DEVICE not in json.dumps(record)

    # @verifies REQ-1402
    # @verifies REQ-1116
    def test_foreign_device_post_is_refused_and_audited(self, as_member, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client, _, dataset = _setup()

        resp = client.post(
            f"/participants/{SUB}/values/rec_participant_points",
            json={"payload": {"device_id": FOREIGN_DEVICE}},
            headers=HEADERS,
        )

        assert resp.status_code == 403
        assert dataset.calls == 0
        [record] = _records(caplog)
        assert record["reason"] == "device_not_owned"

    # @verifies REQ-1402
    # @verifies REQ-1116
    def test_foreign_device_ontology_is_refused_and_audited(self, as_member, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client, _, dataset = _setup()

        resp = client.get(
            f"/participants/{SUB}/ontology/participant_snapshot?device_id={FOREIGN_DEVICE}",
            headers=HEADERS,
        )

        assert resp.status_code == 403
        assert dataset.calls == 0
        [record] = _records(caplog)
        assert record["reason"] == "device_not_owned"

    # @verifies REQ-1402
    def test_a_member_owning_no_meter_names_no_device(self, as_member, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client, _, dataset = _setup(FakeRegistry(devices=()))

        resp = client.get(
            f"/participants/{SUB}/values/meters_data?device_id={OWN_DEVICE}",
            headers=HEADERS,
        )

        assert resp.status_code == 403
        assert dataset.calls == 0

    # @verifies REQ-1404
    def test_failed_ownership_lookup_sends_nothing(self, as_member, caplog):
        caplog.set_level(logging.INFO, logger="celine.audit")
        client, _, dataset = _setup(FakeRegistry(assets_fail=True))

        resp = client.get(
            f"/participants/{SUB}/values/meters_data?device_id={OWN_DEVICE}",
            headers=HEADERS,
        )

        assert resp.status_code == 500
        assert dataset.calls == 0
        [record] = _records(caplog)
        assert record["outcome"] == "error"
