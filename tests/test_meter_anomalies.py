# tests/test_meter_anomalies.py
"""
The meter-anomalies nudge: an event handler with no caller (REQ-1133).

The handler is driven with stand-ins for the values service, the registry client and
the nudging client; the fetch itself goes through the real ``ValuesService`` and
``ValuesFetcher``, so the identity rule is the production one.
"""
from __future__ import annotations

import logging
import types
from typing import Any

import pytest

from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.values.executor import FetcherDescriptor, ValuesFetcher
from celine.dt.core.values.service import ValuesRegistry, ValuesService
from celine.dt.domains.participant.nudging.meters import notify_meters_anomalies

OWNER = "0d6c4f9e-0000-4000-8000-0000000000aa"
COMMUNITY = "example-rec"
DEVICE = "ex-00001"


class _Client:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.calls: list[Any] = []

    async def query(self, *, sql: str, limit: int = 100, offset: int = 0, ctx: Any = None):
        self.calls.append(ctx)
        return self.rows


class _Registry:
    async def lookup_asset_by_sensor_ids(self, sensor_ids: list[str]):
        return [
            types.SimpleNamespace(
                asset_type="meter",
                owner_user_id=OWNER,
                community_key=COMMUNITY,
                name="kitchen meter",
            )
        ]


class _Nudging:
    def __init__(self):
        self.events: list[Any] = []

    async def ingest_event(self, event):
        self.events.append(event)


def _ctx(client: _Client) -> tuple[Any, _Nudging]:
    registry = ValuesRegistry()
    spec = ValueFetcherSpec(id="it-participant.meter_anomalies", client="dataset_api", query="SELECT 1")
    registry.register(FetcherDescriptor(spec=spec, client=client))
    nudging = _Nudging()
    clients = {"rec_registry_admin": _Registry(), "nudging_admin_client": nudging}
    infra = types.SimpleNamespace(
        values_service=ValuesService(registry=registry, fetcher=ValuesFetcher()),
        clients_registry=types.SimpleNamespace(get=clients.__getitem__),
    )
    return types.SimpleNamespace(infra=infra), nudging


class TestMeterAnomalies:
    @pytest.mark.asyncio
    # @verifies REQ-1133
    async def test_reads_as_the_digital_twin_and_nudges_the_owner(self):
        client = _Client([{"device_id": DEVICE, "occurrences_last_hour": 5}])
        ctx, nudging = _ctx(client)
        await notify_meters_anomalies(ctx)
        assert client.calls == [None]
        [event] = nudging.events
        assert event.user_id == OWNER

    @pytest.mark.asyncio
    async def test_debug_log_carries_counts_only(self, caplog):
        caplog.set_level(logging.DEBUG, logger="celine.dt.domains.participant.nudging.meters")
        client = _Client([{"device_id": DEVICE, "occurrences_last_hour": 5}])
        ctx, _ = _ctx(client)
        await notify_meters_anomalies(ctx)
        assert "1 asset(s)" in caplog.text
        for value in (OWNER, COMMUNITY, DEVICE):
            assert value not in caplog.text
