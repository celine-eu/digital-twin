# tests/test_runtime_wiring.py
"""
Startup and wiring rules: the production secret guard, the broker a domain's event
handlers subscribe on, and the ``RunContext`` built from app state.
"""
from __future__ import annotations

import sys
import textwrap
from typing import Any, ClassVar

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from celine.dt.api.dependencies import make_run_context
from celine.dt.contracts.events import DTEvent
from celine.dt.contracts.subscription import EventContext
from celine.dt.core.broker.decorators import on_event
from celine.dt.core.broker.scanner import scan_handlers
from celine.dt.core.broker.service import BrokerService
from celine.dt.core.broker.subscriptions import SubscriptionManager
from celine.dt.core.config import Settings, check_service_credentials
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.domain.registry import DomainRegistry
from celine.sdk.broker import SubscribeResult
from celine.sdk.settings.models import OidcSettings

from tests.conftest import make_infrastructure


# ---------------------------------------------------------------------------
# Production secret guard
# ---------------------------------------------------------------------------

_ENV_NAMES = ("APP_ENV", "CELINE_ENV", "ENV")


def _settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    secret: str | None,
    base_url: str = "http://keycloak.example.org/realms/celine",
    **env: str,
) -> Settings:
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(
        _env_file=None,
        oidc=OidcSettings(
            base_url=base_url, client_id="svc-digital-twin", client_secret=secret
        ),
    )


class TestServiceCredentials:
    # @verifies REQ-1060
    @pytest.mark.parametrize("secret", ["svc-digital-twin", "", None])
    def test_production_refuses_placeholder_secret(self, monkeypatch, secret):
        s = _settings(monkeypatch, secret=secret, APP_ENV="prod")
        with pytest.raises(RuntimeError, match="svc-digital-twin"):
            check_service_credentials(s)

    # @verifies REQ-1060
    def test_production_accepts_real_secret(self, monkeypatch):
        s = _settings(monkeypatch, secret="a-real-secret", APP_ENV="prod")
        check_service_credentials(s)

    # @verifies REQ-1060
    def test_no_client_credentials_no_check(self, monkeypatch):
        s = _settings(monkeypatch, secret="svc-digital-twin", base_url="", APP_ENV="prod")
        check_service_credentials(s)

    # @verifies REQ-1061
    @pytest.mark.parametrize("name", ["dev", "development", "local", "test", "ci", " DEV "])
    def test_non_production_accepts_placeholder(self, monkeypatch, name):
        s = _settings(monkeypatch, secret="svc-digital-twin", APP_ENV=name)
        assert not s.is_production
        check_service_credentials(s)

    # @verifies REQ-1061
    def test_unset_is_production(self, monkeypatch):
        s = _settings(monkeypatch, secret="svc-digital-twin")
        assert s.is_production
        with pytest.raises(RuntimeError):
            check_service_credentials(s)

    # @verifies REQ-1061
    def test_unrecognised_is_production(self, monkeypatch):
        s = _settings(monkeypatch, secret="svc-digital-twin", APP_ENV="staging-ish")
        assert s.is_production

    # @verifies REQ-1061
    @pytest.mark.parametrize("name", ["CELINE_ENV", "ENV"])
    def test_alternative_names(self, monkeypatch, name):
        s = _settings(monkeypatch, secret="svc-digital-twin", **{name: "dev"})
        assert not s.is_production

    # @verifies REQ-1061
    def test_app_env_wins(self, monkeypatch):
        s = _settings(monkeypatch, secret="svc-digital-twin", APP_ENV="prod", ENV="dev")
        assert s.is_production


# ---------------------------------------------------------------------------
# Broker a domain's handlers subscribe on
# ---------------------------------------------------------------------------


class RecordingBrokerService(BrokerService):
    """Records the broker each subscription asked for; connects to nothing."""

    def __init__(self) -> None:
        super().__init__()
        self.subscribed: list[tuple[list[str], str | None]] = []

    async def subscribe(self, *, topics, handler, broker_name=None, qos=None):  # type: ignore[override]
        self.subscribed.append((topics, broker_name))
        return SubscribeResult(success=True, subscription_id=f"s{len(self.subscribed)}")


class EventDomain(DTDomain):
    name: ClassVar[str] = "event-domain"
    domain_type: ClassVar[str] = "test"
    version: ClassVar[str] = "1.0.0"
    route_prefix: ClassVar[str] = "/events"
    entity_id_param: ClassVar[str] = "event_id"

    @on_event("unnamed", topics=["t/unnamed"])
    async def on_unnamed(self, event: DTEvent[Any], ctx: EventContext) -> None: ...

    @on_event("named", topics=["t/named"], broker="explicit")
    async def on_named(self, event: DTEvent[Any], ctx: EventContext) -> None: ...


def _wire(overrides: dict[str, Any]):
    infra = make_infrastructure()
    broker = RecordingBrokerService()
    infra.broker = broker
    domain = EventDomain()
    domain.set_infrastructure(infra.with_overrides(overrides))
    infra._domain_registry = DomainRegistry()
    return infra, broker, domain


def _by_topic(broker: RecordingBrokerService) -> dict[str, str | None]:
    return {topics[0]: name for topics, name in broker.subscribed}


class TestDomainBrokerOverride:
    # @verifies REQ-1070
    @pytest.mark.asyncio
    async def test_domain_method_uses_override(self):
        infra, broker, domain = _wire({"broker": "from-override"})
        await SubscriptionManager(infra=infra, domains=[domain]).start()
        assert _by_topic(broker) == {"t/unnamed": "from-override", "t/named": "explicit"}

    # @verifies REQ-1070
    @pytest.mark.asyncio
    async def test_no_override_uses_default(self):
        infra, broker, domain = _wire({})
        await SubscriptionManager(infra=infra, domains=[domain]).start()
        assert _by_topic(broker) == {"t/unnamed": None, "t/named": "explicit"}

    # @verifies REQ-1070
    def test_scanned_function_uses_override(self, tmp_path, monkeypatch):
        pkg = tmp_path / "dt_scan_fixture"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "domain.py").write_text("")
        (pkg / "events.py").write_text(textwrap.dedent("""
            from celine.dt.core.broker.decorators import on_event

            @on_event("unnamed", topics=["t/unnamed"])
            async def on_unnamed(event, ctx): ...

            @on_event("named", topics=["t/named"], broker="explicit")
            async def on_named(event, ctx): ...
        """))
        monkeypatch.syspath_prepend(str(tmp_path))
        monkeypatch.delitem(sys.modules, "dt_scan_fixture", raising=False)

        _, _, domain = _wire({"broker": "from-override"})
        domain._import_path = "dt_scan_fixture.domain:domain"
        registry = DomainRegistry()
        registry.register(domain)

        specs = scan_handlers(domain_registry=registry)
        brokers = {s.topics[0]: s.metadata["broker"] for s in specs}
        assert brokers == {"t/unnamed": "from-override", "t/named": "explicit"}


# ---------------------------------------------------------------------------
# RunContext from app state
# ---------------------------------------------------------------------------


class TestRunContext:
    def test_reads_app_infrastructure(self):
        infra = make_infrastructure()
        app = FastAPI()
        app.state.infra = infra
        request = Request({"type": "http", "app": app, "headers": []})

        ctx = make_run_context(request)

        assert ctx.values_service is infra.values_service
        assert ctx.broker_service is infra.broker
        assert ctx.services["clients_registry"] is infra.clients_registry
