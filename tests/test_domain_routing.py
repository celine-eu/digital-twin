# tests/test_domain_routing.py
"""
Integration tests for domain-driven routing.

Drives the real router builder and the real FastAPI stack through TestClient. What
the runtime mounts for every domain — `/info`, `/summary`, `/values`,
`/simulations`, `/ontology`, plus the domain's own `routes/` package — is described
in `docs/domains.md`; these tests hold it to that.

The app is wired by `tests/conftest.py:build_app`, which mirrors `create_app`.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import MockDatasetClient, build_app
from tests.sample_domain.domain import (
    SampleCommunityDomain,
    StrictCommunityDomain,
    ValidatingCommunityDomain,
)


BUILTIN_ROUTES = [
    ("GET", "/communities/{community_id}/info"),
    ("GET", "/communities/{community_id}/summary"),
    ("GET", "/communities/{community_id}/values"),
    ("GET", "/communities/{community_id}/values/{fetcher_id}"),
    ("POST", "/communities/{community_id}/values/{fetcher_id}"),
    ("GET", "/communities/{community_id}/values/{fetcher_id}/describe"),
    ("GET", "/communities/{community_id}/simulations"),
    ("GET", "/communities/{community_id}/ontology"),
    ("GET", "/communities/{community_id}/ontology/{spec_id}"),
    ("POST", "/communities/{community_id}/ontology/{spec_id}"),
]


# -- discovery ------------------------------------------------------------------


class TestDiscoveryEndpoints:
    # @verifies REQ-1050
    def test_health(self):
        client = TestClient(build_app(SampleCommunityDomain()))
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    # @verifies REQ-1050
    def test_health_counts_registered_domains(self):
        """`/health` reports the domain count from the live registry.

        It reads through `app.state.infra`, which is the only thing `create_app`
        sets. A version reading a bare `app.state.domain_registry` reports 0 on a
        fully loaded service and looks healthy while doing it.
        """
        client = TestClient(build_app(SampleCommunityDomain(), StrictCommunityDomain()))
        assert client.get("/health").json()["domains"] == 2

    def test_health_reports_broker_absent(self):
        client = TestClient(build_app(SampleCommunityDomain()))
        assert client.get("/health").json()["broker"] == "not configured"

    # @verifies REQ-1051
    def test_domains_list(self):
        client = TestClient(build_app(SampleCommunityDomain()))
        resp = client.get("/domains")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-community"
        assert data[0]["domain_type"] == "energy-community"
        assert data[0]["route_prefix"] == "/communities"
        assert data[0]["entity_id_param"] == "community_id"

    # @verifies REQ-1052
    def test_domains_list_advertises_values(self):
        """The advertised value ids are the domain-local ones, not the namespaced
        registry keys — `describe()` reads the specs, not the registry."""
        client = TestClient(build_app(SampleCommunityDomain()))
        assert client.get("/domains").json()[0]["values"] == ["consumption"]


# -- entity scope ---------------------------------------------------------------


class TestMountedRoutes:
    # @verifies REQ-1020
    def test_every_builtin_route_is_mounted(self):
        """The full built-in surface, asserted as a set rather than one endpoint at a
        time — a route silently dropped from `build_router` is the failure to catch."""
        app = build_app(SampleCommunityDomain())
        mounted = {
            (method, route.path)
            for route in app.routes
            for method in getattr(route, "methods", set()) - {"HEAD"}
        }
        missing = [r for r in BUILTIN_ROUTES if tuple(r) not in mounted]
        assert not missing, f"not mounted: {missing}"


class TestEntityRouting:
    # @verifies REQ-1030
    def test_info(self):
        client = TestClient(build_app(SampleCommunityDomain()))
        resp = client.get("/communities/rec-folgaria/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "test-community"
        assert data["entity"]["id"] == "rec-folgaria"
        assert "request_id" in data
        assert "timestamp" in data

    # @verifies REQ-1032
    def test_info_exposes_resolve_entity_metadata(self):
        client = TestClient(build_app(StrictCommunityDomain()))
        resp = client.get("/strict/abc-123/info")
        assert resp.status_code == 200
        assert resp.json()["entity"]["metadata"] == {"region": "trentino"}

    # @verifies REQ-1031
    def test_entity_resolution_reject(self):
        client = TestClient(build_app(StrictCommunityDomain()))
        assert client.get("/strict/unknown-id/info").status_code == 404

    # @verifies REQ-1030
    def test_entity_resolution_accept(self):
        client = TestClient(build_app(StrictCommunityDomain()))
        resp = client.get("/strict/abc-123/info")
        assert resp.status_code == 200
        assert resp.json()["entity"]["id"] == "abc-123"

    # @verifies REQ-1040
    def test_unauthenticated_is_rejected(self):
        """Every built-in route sits behind `get_ctx_auth`.

        Asserted without the conftest override, because the override is exactly what
        would hide a regression here.
        """
        client = TestClient(build_app(SampleCommunityDomain(), authenticated=False))
        assert client.get("/communities/rec-1/info").status_code == 401

    def test_summary_not_implemented(self):
        """A domain without `get_summary` answers 501, not 500."""
        client = TestClient(build_app(SampleCommunityDomain()))
        assert client.get("/communities/rec-1/summary").status_code == 501

    def test_simulations_not_implemented(self):
        client = TestClient(build_app(SampleCommunityDomain()))
        assert client.get("/communities/rec-1/simulations").status_code == 501


class TestMultipleDomains:
    """Two domains in one app must not bleed into each other.

    The domain is resolved from the URL prefix at request time (`match_path`), not
    bound at mount time, so this is a real risk rather than a formality.
    """

    def test_each_prefix_resolves_its_own_domain(self):
        client = TestClient(build_app(SampleCommunityDomain(), StrictCommunityDomain()))
        assert (
            client.get("/communities/anything/info").json()["domain"]
            == "test-community"
        )
        assert (
            client.get("/strict/abc-123/info").json()["domain"] == "strict-community"
        )

    def test_strict_rules_do_not_apply_to_the_other_domain(self):
        client = TestClient(build_app(SampleCommunityDomain(), StrictCommunityDomain()))
        assert client.get("/strict/nope/info").status_code == 404
        assert client.get("/communities/nope/info").status_code == 200


# -- values ---------------------------------------------------------------------


class TestValueRoutes:
    # @verifies REQ-1100
    # @verifies REQ-1104
    def test_list_values(self):
        client = TestClient(build_app(SampleCommunityDomain()))
        resp = client.get("/communities/rec-1/values")
        assert resp.status_code == 200
        ids = [v["id"] for v in resp.json()]
        # The listing exposes registry keys, which are namespaced.
        assert ids == ["test-community.consumption"]

    # @verifies REQ-1103
    def test_fetch_value_post(self):
        mock = MockDatasetClient(rows=[{"kwh": 10.0}])
        client = TestClient(build_app(SampleCommunityDomain(), client=mock))
        resp = client.post(
            "/communities/rec-1/values/consumption", json={"payload": {}}
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["items"][0]["kwh"] == 10.0

    # @verifies REQ-1032
    def test_fetch_value_post_injects_entity_id(self):
        mock = MockDatasetClient(rows=[])
        client = TestClient(build_app(SampleCommunityDomain(), client=mock))
        client.post("/communities/rec-1/values/consumption", json={"payload": {}})
        assert "rec-1" in mock.last_sql

    # @verifies REQ-1103
    def test_fetch_value_get(self):
        """GET takes the same domain-local id as POST.

        Both endpoints address one resource; the SDK — and therefore every consumer
        — sends the local id. A GET that skipped the namespacing POST applies would
        answer only to the namespaced form, so the two verbs would take different
        identifiers for the same path.
        """
        mock = MockDatasetClient(rows=[{"kwh": 42.0}])
        client = TestClient(build_app(SampleCommunityDomain(), client=mock))
        resp = client.get("/communities/rec-1/values/consumption")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["kwh"] == 42.0
        assert "rec-1" in mock.last_sql

    # @verifies REQ-1201
    def test_fetch_value_get_forwards_query_params_as_payload(self):
        mock = MockDatasetClient(rows=[])
        client = TestClient(build_app(SampleCommunityDomain(), client=mock))
        resp = client.get(
            "/communities/rec-1/values/consumption?since=2026-01-01"
        )
        assert resp.status_code == 200
        # `since` drives a Jinja conditional *and* binds a parameter.
        assert "ts >= '2026-01-01'" in mock.last_sql

    # @verifies REQ-1131
    def test_fetch_value_get_pagination_is_not_payload(self):
        """`limit`/`offset` steer pagination and must not reach the template as
        bind parameters — the query does not declare them."""
        mock = MockDatasetClient(rows=[{"i": i} for i in range(10)])
        client = TestClient(build_app(SampleCommunityDomain(), client=mock))
        resp = client.get("/communities/rec-1/values/consumption?limit=3&offset=2")
        assert resp.status_code == 200
        assert mock.last_limit == 3
        assert mock.last_offset == 2
        assert resp.json()["count"] == 3

    # @verifies REQ-1106
    def test_fetch_value_not_found(self):
        client = TestClient(build_app(SampleCommunityDomain()))
        assert (
            client.get("/communities/rec-1/values/nonexistent").status_code == 404
        )

    # @verifies REQ-1105
    def test_describe_value(self):
        client = TestClient(build_app(SampleCommunityDomain()))
        resp = client.get("/communities/rec-1/values/consumption/describe")
        assert resp.status_code == 200
        assert resp.json()["id"] == "test-community.consumption"

    # @verifies REQ-1106
    def test_fetch_value_post_not_found(self):
        client = TestClient(build_app(SampleCommunityDomain()))
        resp = client.post(
            "/communities/rec-1/values/nonexistent", json={"payload": {}}
        )
        assert resp.status_code == 404

    # @verifies REQ-1106
    def test_describe_unknown_value(self):
        client = TestClient(build_app(SampleCommunityDomain()))
        assert (
            client.get("/communities/rec-1/values/nope/describe").status_code == 404
        )


class TestPayloadValidationOverHttp:
    """The 400 path, end to end.

    The unit tests cover `ValidationError` being raised; these cover it being turned
    into a client error rather than falling into the blanket 500 handler.
    """

    # @verifies REQ-1110
    def test_missing_required_property_is_400(self):
        client = TestClient(build_app(ValidatingCommunityDomain()))
        resp = client.post(
            "/validating/rec-1/values/strict_consumption", json={"payload": {}}
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "validation_error"

    # @verifies REQ-1110
    def test_wrong_type_is_400(self):
        client = TestClient(build_app(ValidatingCommunityDomain()))
        resp = client.post(
            "/validating/rec-1/values/strict_consumption",
            json={"payload": {"zone": "NORD", "days": "seven"}},
        )
        assert resp.status_code == 400

    # @verifies REQ-1111
    def test_valid_payload_succeeds_and_applies_defaults(self):
        mock = MockDatasetClient(rows=[])
        client = TestClient(build_app(ValidatingCommunityDomain(), client=mock))
        resp = client.post(
            "/validating/rec-1/values/strict_consumption",
            json={"payload": {"zone": "NORD"}},
        )
        assert resp.status_code == 200
        assert "'NORD'" in mock.last_sql
        # `days` was never sent; its schema default reached the query.
        assert "days = 7" in mock.last_sql

    # @verifies REQ-1105
    def test_describe_exposes_the_payload_schema(self):
        client = TestClient(build_app(ValidatingCommunityDomain()))
        resp = client.get("/validating/rec-1/values/strict_consumption/describe")
        assert resp.status_code == 200
        schema = resp.json()["spec"]["payload_schema"]
        assert schema["required"] == ["zone"]


# -- custom routes --------------------------------------------------------------


class TestCustomRoutes:
    # @verifies REQ-1021
    def test_discovered_route_is_mounted_under_the_entity_scope(self):
        client = TestClient(build_app(SampleCommunityDomain()))
        resp = client.get("/communities/rec-1/extra/echo")
        assert resp.status_code == 200
        assert resp.json() == {
            "entity_id": "rec-1",
            "domain": "test-community",
            "metadata": {},
        }

    # @verifies REQ-1021
    def test_discovered_route_can_fetch_values(self):
        mock = MockDatasetClient(rows=[{"kwh": 1.0}, {"kwh": 2.0}])
        client = TestClient(build_app(SampleCommunityDomain(), client=mock))
        resp = client.get("/communities/rec-1/extra/via-fetch")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    # @verifies REQ-1022
    def test_a_domain_without_a_routes_package_still_mounts(self):
        """`discover` returning nothing is normal, not an error."""
        client = TestClient(build_app(StrictCommunityDomain()))
        assert client.get("/strict/abc-123/info").status_code == 200


# -- OpenAPI --------------------------------------------------------------------


class TestOperationIds:
    """Operation ids are namespaced per domain.

    This is not cosmetic: `celine-sdk` is generated from this schema, and two
    domains mounting the same built-in routes would otherwise collide on
    `get_info` and generate one method for both.
    """

    def _operation_ids(self, app) -> set[str]:
        return {
            op["operationId"]
            for path in app.openapi()["paths"].values()
            for op in path.values()
            if "operationId" in op
        }

    # @verifies REQ-1023
    def test_ids_are_namespaced_by_domain(self):
        app = build_app(SampleCommunityDomain())
        ids = self._operation_ids(app)
        assert "test_community__get_info" in ids
        assert "get_info" not in ids

    # @verifies REQ-1023
    def test_hyphens_become_underscores(self):
        """A raw hyphen is not a legal identifier in the generated client."""
        ids = self._operation_ids(build_app(SampleCommunityDomain()))
        assert not any("-" in i for i in ids if i.startswith("test_community"))

    # @verifies REQ-1023
    def test_two_domains_do_not_collide(self):
        app = build_app(SampleCommunityDomain(), StrictCommunityDomain())
        ids = self._operation_ids(app)
        assert "test_community__get_info" in ids
        assert "strict_community__get_info" in ids

    # @verifies REQ-1023
    def test_custom_route_ids_are_namespaced_too(self):
        ids = self._operation_ids(build_app(SampleCommunityDomain()))
        assert "test_community__echo" in ids

    # @verifies REQ-1024
    def test_entity_path_parameter_is_documented(self):
        """The path-parameter dependency exists only to make it appear in OpenAPI;
        without it the generated SDK method loses its entity argument."""
        app = build_app(SampleCommunityDomain())
        spec = app.openapi()["paths"]["/communities/{community_id}/info"]["get"]
        assert any(
            p["name"] == "community_id" and p["in"] == "path"
            for p in spec["parameters"]
        )
