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
from celine.dt.core.config import Settings, check_posture
from celine.dt.core.domain.base import DTDomain
from celine.dt.core.domain.registry import DomainRegistry
from celine.sdk.broker import SubscribeResult
from celine.sdk.posture import InsecureConfiguration
from celine.sdk.settings.models import OidcSettings

from tests.conftest import make_infrastructure


# ---------------------------------------------------------------------------
# Startup posture guard
# ---------------------------------------------------------------------------

_ENV_NAMES = ("CELINE_ENV", "ENVIRONMENT", "APP_ENV", "ENV", "DATABASE_URL")
_ISSUER = "http://keycloak.example.org/realms/celine"
_JWKS = f"{_ISSUER}/protocol/openid-connect/certs"
_UNSET = object()


def _settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    secret: str | None,
    base_url: Any = _ISSUER,
    jwks_uri: Any = _JWKS,
    **env: str,
) -> Settings:
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    oidc: dict[str, Any] = {"client_id": "svc-digital-twin", "client_secret": secret}
    if base_url is not _UNSET:
        oidc["base_url"] = base_url
    if jwks_uri is not _UNSET:
        oidc["jwks_uri"] = jwks_uri
    for name in ("CELINE_OIDC_BASE_URL", "CELINE_OIDC_JWKS_URI"):
        monkeypatch.delenv(name, raising=False)
    return Settings(_env_file=None, oidc=OidcSettings(**oidc))


class TestServiceCredentials:
    # @verifies REQ-1060
    @pytest.mark.parametrize("secret", ["svc-digital-twin", "", None])
    def test_production_refuses_placeholder_secret(self, monkeypatch, secret):
        s = _settings(monkeypatch, secret=secret, CELINE_ENV="prod")
        with pytest.raises(InsecureConfiguration, match="svc-digital-twin"):
            check_posture(s)

    # @verifies REQ-1060
    def test_production_accepts_real_secret(self, monkeypatch):
        s = _settings(monkeypatch, secret="a-real-secret", CELINE_ENV="prod")
        check_posture(s)

    # @verifies REQ-1060
    def test_no_client_credentials_no_secret_check(self, monkeypatch):
        s = _settings(monkeypatch, secret="svc-digital-twin", base_url="", CELINE_ENV="prod")
        check_posture(s)

    # @verifies REQ-1061
    @pytest.mark.parametrize("name", ["dev", " DEV "])
    def test_dev_accepts_placeholder(self, monkeypatch, name, caplog):
        s = _settings(
            monkeypatch, secret="svc-digital-twin", base_url=_UNSET, jwks_uri=_UNSET,
            CELINE_ENV=name,
        )
        assert not s.is_production
        check_posture(s, database_url="postgresql://u:securepassword123@db/x")
        assert "development setting" in caplog.text

    # @verifies REQ-1061
    @pytest.mark.parametrize("name", ["development", "local", "test", "ci", "staging", "prod"])
    def test_only_dev_relaxes(self, monkeypatch, name):
        s = _settings(monkeypatch, secret="svc-digital-twin", CELINE_ENV=name)
        assert s.is_production
        with pytest.raises(InsecureConfiguration):
            check_posture(s)

    # @verifies REQ-1061
    def test_unset_is_production(self, monkeypatch):
        s = _settings(monkeypatch, secret="svc-digital-twin")
        assert s.is_production
        assert s.app_env == ""
        with pytest.raises(InsecureConfiguration):
            check_posture(s)

    # @verifies REQ-1061
    def test_unrecognised_is_production(self, monkeypatch):
        s = _settings(monkeypatch, secret="svc-digital-twin", CELINE_ENV="staging-ish")
        assert s.is_production

    # @verifies REQ-1061
    @pytest.mark.parametrize("name", ["ENVIRONMENT", "APP_ENV", "ENV"])
    def test_alternative_names(self, monkeypatch, name):
        s = _settings(monkeypatch, secret="svc-digital-twin", **{name: "dev"})
        assert not s.is_production

    # @verifies REQ-1061
    def test_celine_env_wins(self, monkeypatch):
        s = _settings(monkeypatch, secret="svc-digital-twin", CELINE_ENV="prod", APP_ENV="dev")
        assert s.is_production

    # @verifies REQ-1061
    def test_dotenv_cannot_relax(self, monkeypatch, tmp_path):
        """APP_ENV in a .env file is not the posture signal; only the process env is."""
        dotenv = tmp_path / ".env"
        dotenv.write_text("APP_ENV=dev\nCELINE_ENV=dev\n")
        for name in _ENV_NAMES:
            monkeypatch.delenv(name, raising=False)
        s = Settings(_env_file=str(dotenv))
        assert s.is_production


class TestPostureGuard:
    # @verifies REQ-1062
    @pytest.mark.parametrize(
        ("missing", "setting"),
        [("base_url", "CELINE_OIDC_BASE_URL"), ("jwks_uri", "CELINE_OIDC_JWKS_URI")],
    )
    def test_production_requires_explicit_oidc(self, monkeypatch, missing, setting):
        s = _settings(monkeypatch, secret="a-real-secret", CELINE_ENV="prod", **{missing: _UNSET})
        with pytest.raises(InsecureConfiguration, match=setting):
            check_posture(s)

    # @verifies REQ-1062
    def test_explicit_oidc_from_environment_accepted(self, monkeypatch):
        for name in _ENV_NAMES:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("CELINE_ENV", "prod")
        monkeypatch.setenv("CELINE_OIDC_BASE_URL", _ISSUER)
        monkeypatch.setenv("CELINE_OIDC_JWKS_URI", _JWKS)
        s = Settings(
            _env_file=None,
            oidc=OidcSettings(client_id="svc-digital-twin", client_secret="a-real-secret"),
        )
        check_posture(s)

    # @verifies REQ-1063
    @pytest.mark.parametrize("password", ["securepassword123", "postgres", "changeme"])
    def test_production_refuses_dev_database_password(self, monkeypatch, password):
        s = _settings(monkeypatch, secret="a-real-secret", CELINE_ENV="prod")
        url = f"postgresql+asyncpg://dt:{password}@db.example.org/dt"
        with pytest.raises(InsecureConfiguration, match="DATABASE_URL"):
            check_posture(s, database_url=url)

    # @verifies REQ-1063
    def test_database_url_read_from_environment(self, monkeypatch):
        s = _settings(
            monkeypatch, secret="a-real-secret", CELINE_ENV="prod",
            DATABASE_URL="postgresql://dt:postgres@db.example.org/dt",
        )
        with pytest.raises(InsecureConfiguration, match="DATABASE_URL"):
            check_posture(s)

    # @verifies REQ-1063
    def test_production_accepts_real_database_password(self, monkeypatch):
        s = _settings(
            monkeypatch, secret="a-real-secret", CELINE_ENV="prod",
            DATABASE_URL="postgresql://dt:Zq8-generated@db.example.org/dt",
        )
        check_posture(s)

    # @verifies REQ-1062
    def test_production_reports_every_violation_at_once(self, monkeypatch):
        s = _settings(
            monkeypatch, secret="svc-digital-twin", base_url=_UNSET, jwks_uri=_UNSET,
            CELINE_ENV="staging",
        )
        with pytest.raises(InsecureConfiguration) as err:
            check_posture(s, database_url="postgresql://u:securepassword123@db/x")
        text = str(err.value)
        for setting in (
            "CELINE_OIDC_BASE_URL", "CELINE_OIDC_JWKS_URI",
            "CELINE_OIDC_CLIENT_SECRET", "DATABASE_URL",
        ):
            assert setting in text


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
