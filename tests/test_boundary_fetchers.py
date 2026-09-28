# tests/test_boundary_fetchers.py
"""
The reference-boundary fetchers, `boundary_at_point` and `boundary_shape` (ADR-0003).

Three layers, each checking something the others cannot:

* **the declaration**: the payload schemas, the limits, the source enum;
* **the rendered SQL**: what statement reaches the data client for a point inside,
  outside, on an edge, in an overlap, an unknown source, empty ids and a quote in an id;
* **over HTTP, against a fake dataset-api**: the real `DatasetSqlApiClient` behind the
  real router, with httpx answered by `_FakeDatasetApi`. The fake keeps a few synthetic
  rectangles and answers the point query with PostGIS's semantics for the predicate the
  statement uses: `ST_Intersects` of a point and a polygon includes the polygon's edge
  (it is `ST_Covers` for a point), `ST_Contains` excludes it. It orders by id and applies
  the `limit` the client sent, as dataset-api does after the statement's `ORDER BY`.

The fake is not PostGIS. The same rendered statements were run once against PostGIS
(dataset-api's disposable test database, synthetic squares; 2026-09-27) and answered as
these tests expect: inside, outside, a shared edge and a shared corner resolving to the
lowest id, an overlap resolving to the lowest id, unknown ids absent. Geometries and ids
here are synthetic.
"""

from __future__ import annotations

import json
import logging
import re
import types
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from celine.dt.contracts.entity import EntityInfo
from celine.dt.core.clients import dataset_api as dataset_api_module
from celine.dt.core.clients.dataset_api import DatasetSqlApiClient
from celine.dt.core.values.template import render_query
from celine.dt.domains.energy_community.base import EnergyCommunityDomain
from celine.dt.domains.energy_community.boundary_fetchers import (
    BOUNDARY_SHAPE_MAX_IDS,
    BOUNDARY_SOURCES,
    boundary_value_specs,
)
from celine.dt.domains.energy_community.domain import ITEnergyCommunityDomain
from tests.conftest import MockDatasetClient, build_app

SOURCE = "gse_cabine_primarie"
BASE = "/communities/it/rec-1/values"

# Synthetic rectangles (lon_min, lat_min, lon_max, lat_max), placeholder ids.
# 02 and 01 share the edge lon=1; 04 sits on top of 01 sharing lat=1; 03 overlaps 04.
SHAPES: dict[str, tuple[float, float, float, float]] = {
    "AC000E00002": (0.0, 0.0, 1.0, 1.0),
    "AC000E00001": (1.0, 0.0, 2.0, 1.0),
    "AC000E00004": (1.0, 1.0, 2.0, 2.0),
    "AC000E00003": (1.2, 1.2, 3.0, 3.0),
}


def _specs() -> dict[str, Any]:
    return {spec.id: spec for spec in boundary_value_specs()}


def _render(fetcher: str, **params: Any) -> str:
    entity = EntityInfo(id="rec-1", domain_name="it-energy-community")
    return render_query(_specs()[fetcher].query, entity=entity, params=params)


def _app(client: Any | None = None) -> TestClient:
    return TestClient(build_app(ITEnergyCommunityDomain(), client=client or MockDatasetClient()))


# -- the fake dataset-api ---------------------------------------------------------


class _FakeDatasetApi:
    """Answers `POST /query` for the two boundary statements over `SHAPES`."""

    POINT = re.compile(r"ST_Point\(\s*(-?[\d.eE+-]+)\s*,\s*(-?[\d.eE+-]+)\s*\)")
    IN_LIST = re.compile(r"boundary\.id IN \((.*)\)", re.DOTALL)

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/query"
        body = json.loads(request.content)
        self.requests.append(body)
        sql: str = body["sql"]
        assert "FROM ds_dev_gold.gse_cabine_primarie" in sql

        if "ST_AsGeoJSON" in sql:
            rows = self._shapes(sql)
        else:
            rows = self._at_point(sql)
        rows.sort(key=lambda r: r["id"])
        start = body.get("offset", 0)
        return httpx.Response(200, json={"items": rows[start : start + body["limit"]]})

    def _at_point(self, sql: str) -> list[dict[str, Any]]:
        match = self.POINT.search(sql)
        assert match, sql
        lon, lat = float(match.group(1)), float(match.group(2))
        if "ST_Intersects(" in sql:
            edge_is_inside = True  # interior or edge
        elif "ST_Contains(" in sql:
            edge_is_inside = False  # interior only
        else:
            raise AssertionError(f"no spatial predicate in {sql}")

        def covers(a: float, v: float, b: float) -> bool:
            return a <= v <= b if edge_is_inside else a < v < b

        return [
            {"id": key}
            for key, (x0, y0, x1, y1) in SHAPES.items()
            if covers(x0, lon, x1) and covers(y0, lat, y1)
        ]

    def _shapes(self, sql: str) -> list[dict[str, Any]]:
        if "WHERE FALSE" in sql:
            return []
        match = self.IN_LIST.search(sql)
        assert match, sql
        # Undo sql_quote: split on the separator between literals, then un-double.
        inner = match.group(1).strip()
        requested = [lit.replace("''", "'") for lit in re.findall(r"'((?:[^']|'')*)'", inner)]
        rows = []
        for key in requested:
            if key in SHAPES:
                x0, y0, x1, y1 = SHAPES[key]
                ring = [[x0, y0], [x0, y1], [x1, y1], [x1, y0], [x0, y0]]
                rows.append(
                    {"id": key, "geojson": json.dumps({"type": "Polygon", "coordinates": [ring]})}
                )
        return rows


@pytest.fixture
def fake_dataset_api(monkeypatch):
    """The real client, with its httpx calls answered by `_FakeDatasetApi`."""
    fake = _FakeDatasetApi()
    real_async_client = httpx.AsyncClient

    def _client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real_async_client(*args, transport=httpx.MockTransport(fake.handler), **kwargs)

    monkeypatch.setattr(
        dataset_api_module,
        "httpx",
        types.SimpleNamespace(AsyncClient=_client, HTTPStatusError=httpx.HTTPStatusError),
    )
    fake.client = TestClient(  # type: ignore[attr-defined]
        build_app(
            ITEnergyCommunityDomain(),
            client=DatasetSqlApiClient(
                base_url="http://dataset-api.test",
                token_provider=_FakeTokenProvider(SERVICE_TOKEN),
            ),
        )
    )
    return fake


def _at_point(fake: _FakeDatasetApi, lat: float, lon: float) -> list[dict[str, Any]]:
    resp = fake.client.post(  # type: ignore[attr-defined]
        f"{BASE}/boundary_at_point",
        json={"payload": {"source": SOURCE, "lat": lat, "lon": lon}},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


# -- declaration ------------------------------------------------------------------


class TestDeclaration:
    # @verifies REQ-1150
    def test_both_fetchers_declare_source_as_a_required_closed_enum(self):
        assert BOUNDARY_SOURCES == ("gse_cabine_primarie",)
        for fetcher in ("boundary_at_point", "boundary_shape"):
            schema = _specs()[fetcher].payload_schema
            assert "source" in schema["required"]
            assert schema["properties"]["source"]["enum"] == ["gse_cabine_primarie"]
            assert schema["additionalProperties"] is False

    # @verifies REQ-1150
    def test_declared_in_the_base_domain_and_inherited_by_the_italian_one(self):
        """ADR-0003: the base class declares them, so every locale variant has them."""

        class _OtherLocale(EnergyCommunityDomain):
            name = "xx-energy-community"
            route_prefix = "/communities/xx"

        for domain in (_OtherLocale(), ITEnergyCommunityDomain()):
            ids = [spec.id for spec in domain.get_value_specs()]
            assert "boundary_at_point" in ids
            assert "boundary_shape" in ids

    # @verifies REQ-1150
    def test_describe_publishes_the_enum(self):
        resp = _app().get(f"{BASE}/boundary_at_point/describe")
        assert resp.status_code == 200
        props = resp.json()["spec"]["payload_schema"]["properties"]
        assert props["source"]["enum"] == ["gse_cabine_primarie"]

    # @verifies REQ-1159
    def test_shape_limit_covers_the_widest_request(self):
        spec = _specs()["boundary_shape"]
        max_items = spec.payload_schema["properties"]["ids"]["maxItems"]
        assert max_items == BOUNDARY_SHAPE_MAX_IDS
        assert spec.limit >= max_items

    # @verifies REQ-1153
    def test_at_point_answers_at_most_one_row(self):
        assert _specs()["boundary_at_point"].limit == 1


# -- source selection -------------------------------------------------------------


class TestSource:
    @pytest.mark.parametrize(
        "fetcher,payload",
        [
            ("boundary_at_point", {"lat": 0.5, "lon": 0.5}),
            ("boundary_shape", {"ids": ["AC000E00001"]}),
        ],
    )
    @pytest.mark.parametrize(
        "source", ["nuts", "ds_dev_gold.users", "gse_cabine_primarie; DROP TABLE x", ""]
    )
    # @verifies REQ-1151
    def test_unknown_source_is_400_and_never_reaches_the_client(self, fetcher, payload, source):
        mock = MockDatasetClient(rows=[{"id": "AC000E00001"}])
        resp = _app(mock).post(f"{BASE}/{fetcher}", json={"payload": {"source": source, **payload}})
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "validation_error"
        assert mock.calls == 0

    # @verifies REQ-1151
    def test_missing_source_is_400(self):
        mock = MockDatasetClient()
        resp = _app(mock).post(
            f"{BASE}/boundary_at_point", json={"payload": {"lat": 0.5, "lon": 0.5}}
        )
        assert resp.status_code == 400
        assert mock.calls == 0

    # @verifies REQ-1214
    @pytest.mark.parametrize("fetcher", ["boundary_at_point", "boundary_shape"])
    def test_a_value_with_no_branch_fails_rendering(self, fetcher):
        """The enum and the branches drifting apart must not fall through to a table."""
        with pytest.raises(ValueError, match="Query template error"):
            _render(fetcher, source="nuts", lat=0.5, lon=0.5, ids=["AC000E00001"])

    # @verifies REQ-1214
    @pytest.mark.parametrize("source", BOUNDARY_SOURCES)
    def test_every_enum_value_has_a_branch_naming_its_table(self, source):
        sql = _render("boundary_at_point", source=source, lat=0.5, lon=0.5)
        assert "FROM ds_dev_gold.gse_cabine_primarie" in sql

    # @verifies REQ-1214
    @pytest.mark.parametrize("fetcher", ["boundary_at_point", "boundary_shape"])
    def test_the_source_value_is_never_interpolated(self, fetcher):
        query = _specs()[fetcher].query
        assert re.search(r"\{\{\s*source\b", query) is None
        assert ":source" not in query
        assert 'source == "gse_cabine_primarie"' in query


# -- boundary_at_point ------------------------------------------------------------


class TestAtPointPayload:
    @pytest.mark.parametrize(
        "lat,lon",
        [(90.5, 0), (-90.5, 0), (0, 180.5), (0, -180.5), ("45.1", 11.1), (45.1, None), (True, 1)],
    )
    # @verifies REQ-1152
    def test_out_of_range_or_not_a_number_is_400(self, lat, lon):
        mock = MockDatasetClient()
        resp = _app(mock).post(
            f"{BASE}/boundary_at_point",
            json={"payload": {"source": SOURCE, "lat": lat, "lon": lon}},
        )
        assert resp.status_code == 400
        assert mock.calls == 0

    @pytest.mark.parametrize("field", ["lat", "lon"])
    # @verifies REQ-1152
    # @verifies REQ-1115
    def test_nan_is_400_and_never_reaches_the_client(self, field):
        """NaN passes minimum/maximum; it must not reach the statement as `nan`."""
        mock = MockDatasetClient()
        payload = {"source": SOURCE, "lat": "0.5", "lon": "0.5"}
        payload[field] = "NaN"
        body = '{"payload": {"source": "%s", "lat": %s, "lon": %s}}' % (
            SOURCE,
            payload["lat"],
            payload["lon"],
        )
        resp = _app(mock).post(
            f"{BASE}/boundary_at_point",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "validation_error"
        assert mock.calls == 0

    @pytest.mark.parametrize("missing", ["lat", "lon"])
    # @verifies REQ-1152
    def test_lat_and_lon_are_required(self, missing):
        payload = {"source": SOURCE, "lat": 0.5, "lon": 0.5}
        del payload[missing]
        resp = _app().post(f"{BASE}/boundary_at_point", json={"payload": payload})
        assert resp.status_code == 400

    @pytest.mark.parametrize("lat,lon", [(90, 180), (-90, -180), (0, 0), (45, 11)])
    # @verifies REQ-1152
    def test_range_limits_and_integers_are_accepted(self, lat, lon):
        mock = MockDatasetClient()
        resp = _app(mock).post(
            f"{BASE}/boundary_at_point",
            json={"payload": {"source": SOURCE, "lat": lat, "lon": lon}},
        )
        assert resp.status_code == 200
        assert mock.calls == 1


class TestAtPointSql:
    # @verifies REQ-1153
    def test_the_point_is_lon_lat_in_wgs84_and_bound_as_numbers(self):
        sql = _render("boundary_at_point", source=SOURCE, lat=0.25, lon=0.75)
        assert "ST_SetSRID(ST_Point(0.75, 0.25), 4326)" in sql

    # @verifies REQ-1152
    # @verifies REQ-1153
    def test_a_negative_point_renders_as_signed_numeric_literals(self):
        """South of the equator and west of Greenwich: a unary minus on each literal.

        dataset-api admits a unary minus on a numeric literal (its QE-02); the schema here
        already admits the negative half of each range (REQ-1152), so the statement must
        carry the sign on the literal and nothing else: no quotes, no cast, no spacing
        that turns it into a binary minus.
        """
        sql = _render("boundary_at_point", source=SOURCE, lat=-0.05, lon=-0.3)
        assert "ST_SetSRID(ST_Point(-0.3, -0.05), 4326)" in sql
        assert "'-" not in sql

    # @verifies REQ-1152
    def test_a_negative_point_reaches_the_client_signed(self, fake_dataset_api):
        assert _at_point(fake_dataset_api, lat=-0.05, lon=-0.3) == []
        assert "ST_Point(-0.3, -0.05)" in fake_dataset_api.requests[-1]["sql"]

    # @verifies REQ-1127
    def test_a_point_lookup_never_logs_the_statement_or_the_point(self, fake_dataset_api, caplog):
        # The `celine` logger sits at INFO; the fetch line is DEBUG.
        caplog.set_level(logging.DEBUG, logger="celine.dt.core.values.executor")
        assert _at_point(fake_dataset_api, lat=0.012345, lon=0.312345) == [{"id": "AC000E00002"}]
        assert "ST_Point(0.312345, 0.012345)" in fake_dataset_api.requests[-1]["sql"]
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "boundary_at_point" in text
        for literal in ("0.012345", "0.312345", "SELECT", "ST_Point", "ST_Intersects"):
            assert literal not in text

    # @verifies REQ-1153
    def test_covers_semantics_the_edge_is_inside(self):
        """ST_Intersects(polygon, point) is true on the edge; ST_Contains is not."""
        sql = _render("boundary_at_point", source=SOURCE, lat=0.5, lon=1.0)
        assert "ST_Intersects(" in sql
        assert "ST_Contains(" not in sql
        assert "ST_Within(" not in sql

    # @verifies REQ-1155
    def test_several_covering_shapes_resolve_to_the_lowest_id(self):
        sql = _render("boundary_at_point", source=SOURCE, lat=1.5, lon=1.5)
        assert re.search(r"ORDER BY boundary\.id ASC\s*$", sql)


class TestAtPointOverHttp:
    # @verifies REQ-1153
    def test_inside(self, fake_dataset_api):
        assert _at_point(fake_dataset_api, lat=0.5, lon=0.5) == [{"id": "AC000E00002"}]
        assert fake_dataset_api.requests[-1]["limit"] == 1

    # @verifies REQ-1154
    def test_outside_every_shape_is_200_with_no_rows(self, fake_dataset_api):
        assert _at_point(fake_dataset_api, lat=5.0, lon=5.0) == []

    # @verifies REQ-1153
    # @verifies REQ-1155
    def test_on_a_shared_edge_is_inside_and_resolves_to_the_lowest_id(self, fake_dataset_api):
        # lon=1 is the edge 02 and 01 share: both cover it, 01 is lower.
        assert _at_point(fake_dataset_api, lat=0.5, lon=1.0) == [{"id": "AC000E00001"}]

    # @verifies REQ-1153
    def test_on_an_outer_edge_is_inside(self, fake_dataset_api):
        assert _at_point(fake_dataset_api, lat=0.0, lon=0.5) == [{"id": "AC000E00002"}]

    # @verifies REQ-1155
    def test_on_a_shared_corner_resolves_to_the_lowest_id(self, fake_dataset_api):
        # (1, 1) is on 02, 01 and 04.
        assert _at_point(fake_dataset_api, lat=1.0, lon=1.0) == [{"id": "AC000E00001"}]

    # @verifies REQ-1155
    def test_in_an_overlap_resolves_to_the_lowest_id_on_every_call(self, fake_dataset_api):
        # (1.5, 1.5) is inside both 04 and 03.
        answers = [_at_point(fake_dataset_api, lat=1.5, lon=1.5) for _ in range(3)]
        assert answers == [[{"id": "AC000E00003"}]] * 3


# -- boundary_shape ---------------------------------------------------------------


class TestShapeSql:
    # @verifies REQ-1156
    def test_selects_exactly_the_requested_ids_as_simplified_geojson(self):
        sql = _render("boundary_shape", source=SOURCE, ids=["AC000E00001", "AC000E00002"])
        assert "WHERE boundary.id IN ('AC000E00001', 'AC000E00002')" in sql
        assert "ST_AsGeoJSON(" in sql
        assert "ST_Simplify(boundary.geometry, 0.0001, TRUE)" in sql

    # @verifies REQ-1158
    def test_empty_ids_render_no_list(self):
        sql = _render("boundary_shape", source=SOURCE, ids=[])
        assert "WHERE FALSE" in sql
        assert " IN " not in sql
        assert "()" not in sql

    # @verifies REQ-1156
    def test_a_quote_in_an_id_stays_inside_its_literal(self):
        sql = _render("boundary_shape", source=SOURCE, ids=["AC000E00001", "x') OR ('1'='1"])
        assert "IN ('AC000E00001', 'x'') OR (''1''=''1')" in sql

    # @verifies REQ-1156
    # @verifies REQ-1215
    def test_a_colon_name_in_an_id_is_not_substituted(self):
        """An id carrying `:ids` or `:source` must stay inside its own literal."""
        ids = ["x:ids", ") OR TRUE UNION SELECT 1 --", "y:source"]
        sql = _render("boundary_shape", source=SOURCE, ids=ids)
        assert "IN ('x:ids', ') OR TRUE UNION SELECT 1 --', 'y:source')" in sql


class TestShapePayload:
    # @verifies REQ-1159
    def test_more_ids_than_max_items_is_400(self):
        mock = MockDatasetClient()
        ids = [f"ex-{n:05d}" for n in range(BOUNDARY_SHAPE_MAX_IDS + 1)]
        resp = _app(mock).post(
            f"{BASE}/boundary_shape", json={"payload": {"source": SOURCE, "ids": ids}}
        )
        assert resp.status_code == 400
        assert mock.calls == 0

    # @verifies REQ-1159
    def test_max_items_ids_are_all_answered(self):
        ids = [f"ex-{n:05d}" for n in range(BOUNDARY_SHAPE_MAX_IDS)]
        mock = MockDatasetClient(rows=[{"id": i, "geojson": "{}"} for i in ids])
        resp = _app(mock).post(
            f"{BASE}/boundary_shape", json={"payload": {"source": SOURCE, "ids": ids}}
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == BOUNDARY_SHAPE_MAX_IDS
        assert mock.last_limit >= BOUNDARY_SHAPE_MAX_IDS

    # @verifies REQ-1156
    def test_ids_is_required(self):
        resp = _app().post(f"{BASE}/boundary_shape", json={"payload": {"source": SOURCE}})
        assert resp.status_code == 400


class TestShapeOverHttp:
    def _shapes(self, fake, ids):
        resp = fake.client.post(
            f"{BASE}/boundary_shape", json={"payload": {"source": SOURCE, "ids": ids}}
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["items"]

    # @verifies REQ-1156
    def test_one_row_per_requested_id_with_its_geojson(self, fake_dataset_api):
        rows = self._shapes(fake_dataset_api, ["AC000E00002", "AC000E00001"])
        assert [r["id"] for r in rows] == ["AC000E00001", "AC000E00002"]
        for row in rows:
            assert json.loads(row["geojson"])["type"] == "Polygon"

    # @verifies REQ-1157
    def test_an_unknown_id_is_absent_not_an_error(self, fake_dataset_api):
        rows = self._shapes(fake_dataset_api, ["AC000E00001", "AC000E00009"])
        assert [r["id"] for r in rows] == ["AC000E00001"]

    # @verifies REQ-1156
    # @verifies REQ-1157
    def test_a_quoted_id_is_an_unknown_id_not_an_injection(self, fake_dataset_api):
        rows = self._shapes(fake_dataset_api, ["x') OR ('1'='1"])
        assert rows == []

    # @verifies REQ-1157
    # @verifies REQ-1215
    def test_ids_carrying_colon_names_are_unknown_ids_not_an_injection(self, fake_dataset_api):
        rows = self._shapes(
            fake_dataset_api, ["x:ids", ") OR TRUE UNION SELECT 1 --", "AC000E00001"]
        )
        assert [r["id"] for r in rows] == ["AC000E00001"]
        sent = fake_dataset_api.requests[-1]["sql"]
        assert "IN ('x:ids', ') OR TRUE UNION SELECT 1 --', 'AC000E00001')" in sent

    # @verifies REQ-1158
    def test_empty_ids_is_200_with_no_rows_and_no_list_sent(self, fake_dataset_api):
        assert self._shapes(fake_dataset_api, []) == []
        sent = fake_dataset_api.requests[-1]["sql"]
        assert "()" not in sent
        assert " IN " not in sent


# -- whose token reaches dataset-api (D47) ----------------------------------------


class _FakeTokenProvider:
    """The Digital Twin's own client-credentials provider, minus Keycloak."""

    def __init__(self, access_token: str) -> None:
        self.access_token = access_token
        self.calls = 0

    async def get_token(self) -> Any:
        self.calls += 1
        return types.SimpleNamespace(access_token=self.access_token)


CALLER_TOKEN = "caller-token-synthetic"
SERVICE_TOKEN = "dt-service-token-synthetic"


@pytest.fixture
def token_recorder(monkeypatch):
    return _recorder(monkeypatch, _FakeTokenProvider(SERVICE_TOKEN))


class _FailingTokenProvider:
    """A configured provider whose identity provider is down or refuses the client."""

    def __init__(self) -> None:
        self.calls = 0

    async def get_token(self) -> Any:
        self.calls += 1
        raise httpx.HTTPStatusError(
            "token endpoint refused",
            request=httpx.Request("POST", "https://idp.example.org/token"),
            response=httpx.Response(503),
        )


@pytest.fixture
def failing_provider_recorder(monkeypatch):
    """The same app, with a token provider that cannot obtain a token."""
    return _recorder(monkeypatch, _FailingTokenProvider())


@pytest.fixture
def unconfigured_recorder(monkeypatch):
    """The same app, with no token provider: a deployment without OIDC client credentials."""
    return _recorder(monkeypatch, None)


def _recorder(monkeypatch, provider: Any) -> Any:
    """The real client and the real ``get_ctx_auth``, recording each Authorization sent.

    Only the JWT verification is replaced (any non-empty bearer is a user), so the
    route's authentication requirement is the production one.
    """
    from celine.dt.api import context as context_module

    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"items": []})

    real_async_client = httpx.AsyncClient

    def _client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real_async_client(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(
        dataset_api_module,
        "httpx",
        types.SimpleNamespace(AsyncClient=_client, HTTPStatusError=httpx.HTTPStatusError),
    )
    monkeypatch.setattr(
        context_module,
        "parse_jwt_user",
        lambda token: types.SimpleNamespace(sub="synthetic") if token else None,
    )
    client = TestClient(
        build_app(
            ITEnergyCommunityDomain(),
            client=DatasetSqlApiClient(
                base_url="http://dataset-api.test", token_provider=provider
            ),
            authenticated=False,
        )
    )
    return types.SimpleNamespace(client=client, seen=seen, provider=provider)


def _as_caller(rec: Any, fetcher: str, payload: dict[str, Any]) -> httpx.Response:
    return rec.client.post(
        f"{BASE}/{fetcher}",
        json={"payload": payload},
        headers={"Authorization": f"Bearer {CALLER_TOKEN}"},
    )


class TestServiceIdentity:
    @pytest.mark.parametrize(
        "fetcher,payload",
        [
            ("boundary_at_point", {"source": SOURCE, "lat": 0.05, "lon": 0.2}),
            ("boundary_shape", {"source": SOURCE, "ids": ["AC000E00001"]}),
        ],
    )
    # @verifies REQ-1125
    # @verifies REQ-1160
    def test_boundary_fetchers_send_the_dt_token_not_the_callers(
        self, token_recorder, fetcher, payload
    ):
        resp = _as_caller(token_recorder, fetcher, payload)
        assert resp.status_code == 200, resp.text
        assert token_recorder.seen == [f"Bearer {SERVICE_TOKEN}"]
        assert CALLER_TOKEN not in token_recorder.seen[0]
        assert token_recorder.provider.calls == 1

    # @verifies REQ-1121
    # @verifies REQ-1128
    # @verifies REQ-1160
    def test_any_other_fetcher_forwards_the_callers_token(self, token_recorder):
        resp = _as_caller(token_recorder, "rec_flexibility_windows", {})
        assert resp.status_code == 200, resp.text
        # One scheme, then the caller's token: never `Bearer Bearer <token>`.
        assert token_recorder.seen == [f"Bearer {CALLER_TOKEN}"]
        assert token_recorder.provider.calls == 0

    @pytest.mark.parametrize(
        "fetcher,payload",
        [
            ("boundary_at_point", {"source": SOURCE, "lat": 0.05, "lon": 0.2}),
            ("boundary_shape", {"source": SOURCE, "ids": ["AC000E00001"]}),
        ],
    )
    # @verifies REQ-1125
    def test_the_caller_must_still_be_authenticated(self, token_recorder, fetcher, payload):
        resp = token_recorder.client.post(f"{BASE}/{fetcher}", json={"payload": payload})
        assert resp.status_code == 401
        assert token_recorder.seen == []
        assert token_recorder.provider.calls == 0

    # @verifies REQ-1160
    def test_only_the_boundary_fetchers_declare_the_service_identity(self):
        from celine.dt.core.domain.config import load_domains_config
        from celine.dt.core.loader import import_attr

        service = set()
        for spec in load_domains_config(["config/domains.yaml"]).domains:
            domain = import_attr(spec.import_path)
            for fetcher in domain.get_value_specs():
                assert fetcher.identity in ("caller", "service")
                if fetcher.identity == "service":
                    service.add((domain.name, fetcher.id))
        assert {fid for _, fid in service} == {"boundary_at_point", "boundary_shape"}
        assert all(name.endswith("energy-community") for name, _ in service)


# -- privacy ----------------------------------------------------------------------


class TestNoServiceIdentity:
    """REQ-1129: no token provider, so the Digital Twin has no identity of its own."""

    @pytest.mark.parametrize(
        "fetcher,payload",
        [
            ("boundary_at_point", {"source": SOURCE, "lat": 0.05, "lon": 0.2}),
            ("boundary_shape", {"source": SOURCE, "ids": ["AC000E00001"]}),
        ],
    )
    # @verifies REQ-1129
    def test_a_service_fetcher_answers_503_and_sends_nothing(
        self, unconfigured_recorder, fetcher, payload
    ):
        resp = _as_caller(unconfigured_recorder, fetcher, payload)
        assert resp.status_code == 503, resp.text
        assert resp.json()["detail"]["error"] == "service_identity_unavailable"
        assert unconfigured_recorder.seen == []

    # @verifies REQ-1129
    def test_the_503_logs_no_coordinate(self, unconfigured_recorder, caplog):
        caplog.set_level(logging.DEBUG)
        _as_caller(
            unconfigured_recorder,
            "boundary_at_point",
            {"source": SOURCE, "lat": 0.123457, "lon": 0.765431},
        )
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "service_identity_unavailable" in text
        assert "0.123457" not in text
        assert "0.765431" not in text

    @pytest.mark.parametrize(
        "fetcher,payload",
        [
            ("boundary_at_point", {"source": SOURCE, "lat": 0.05, "lon": 0.2}),
            ("boundary_shape", {"source": SOURCE, "ids": ["AC000E00001"]}),
        ],
    )
    # @verifies REQ-1129
    def test_a_provider_that_cannot_get_a_token_answers_503_and_sends_nothing(
        self, failing_provider_recorder, fetcher, payload
    ):
        resp = _as_caller(failing_provider_recorder, fetcher, payload)
        assert resp.status_code == 503, resp.text
        assert resp.json()["detail"]["error"] == "service_identity_unavailable"
        assert failing_provider_recorder.seen == []
        assert failing_provider_recorder.provider.calls == 1

    # @verifies REQ-1129
    def test_the_token_failure_503_logs_no_coordinate_nor_idp_detail(
        self, failing_provider_recorder, caplog
    ):
        caplog.set_level(logging.DEBUG)
        _as_caller(
            failing_provider_recorder,
            "boundary_at_point",
            {"source": SOURCE, "lat": 0.123457, "lon": 0.765431},
        )
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "service_identity_unavailable" in text
        assert "0.123457" not in text
        assert "0.765431" not in text
        assert "idp.example.org" not in text

    # @verifies REQ-1121
    # @verifies REQ-1129
    def test_a_caller_fetcher_still_forwards_the_callers_token(self, unconfigured_recorder):
        resp = _as_caller(unconfigured_recorder, "rec_flexibility_windows", {})
        assert resp.status_code == 200, resp.text
        assert unconfigured_recorder.seen == [f"Bearer {CALLER_TOKEN}"]


class TestNoCoordinatesInLogs:
    """A supply address's point is personal data: nothing may log it."""

    def test_a_successful_lookup_logs_no_coordinate(self, fake_dataset_api, caplog):
        caplog.set_level(logging.DEBUG)
        _at_point(fake_dataset_api, lat=0.123457, lon=0.765431)
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "0.123457" not in text
        assert "0.765431" not in text

    def test_a_refused_lookup_logs_no_coordinate(self, caplog):
        caplog.set_level(logging.DEBUG)
        resp = _app().post(
            f"{BASE}/boundary_at_point",
            json={"payload": {"source": SOURCE, "lat": 91.123457, "lon": "11.765431"}},
        )
        assert resp.status_code == 400
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "91.123457" not in text
        assert "11.765431" not in text
