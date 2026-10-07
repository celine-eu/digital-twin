# tests/test_community_scoping.py
"""
Which community a community-domain fetch reads (docs/specifications/community.md), and the
participant domain's community-wide forecast (REQ-1405).

Asserted on the rendered statement: the predicate is the only thing that keeps one
community's rows out of another's answer when the caller holds a service token, which
dataset-api does not narrow.
"""
from __future__ import annotations

import re

import pytest

from celine.dt.contracts.entity import EntityInfo
from celine.dt.core.values.template import render_query
from celine.dt.domains.energy_community.domain import ITEnergyCommunityDomain
from celine.dt.domains.participant.domain import ITParticipantDomain

REC_TABLE = re.compile(
    r"FROM\s+ds_dev_gold\.(rec_\w+|meters_\w+|cer_energy_forecast)", re.IGNORECASE
)
SCOPE = "community_id = {{ entity.id | sql_quote }}"


def _community_specs():
    return {s.id: s for s in ITEnergyCommunityDomain().get_value_specs()}


def _params(spec) -> dict:
    """A value for every bind parameter, so the statement renders whole."""
    names = re.findall(r"(?<!:):([a-zA-Z_]\w*)", spec.query or "")
    return {n: "2026-01-01" for n in names}


def _rec_specs():
    return [s for s in _community_specs().values() if REC_TABLE.search(s.query or "")]


def test_the_domain_has_rec_fetchers_to_scope() -> None:
    ids = {s.id for s in _rec_specs()}
    assert {"rec_self_consumption", "rec_population_summary", "rec_flexibility_chain_daily"} <= ids


@pytest.mark.parametrize("spec", _rec_specs(), ids=lambda s: s.id)
def test_every_rec_read_names_the_community(spec) -> None:
    """@verifies REQ-1500"""
    query = spec.query or ""
    reads = len(REC_TABLE.findall(query))
    assert query.count(SCOPE) == reads, (
        f"{spec.id}: {reads} REC read(s), {query.count(SCOPE)} restricted to the community"
    )
    rendered = render_query(
        query, entity=EntityInfo(id="example-rec", domain_name="it-energy-community"),
        params=_params(spec),
    )
    assert rendered.count("community_id = 'example-rec'") == reads


@pytest.mark.parametrize("spec", _rec_specs(), ids=lambda s: s.id)
def test_the_entity_id_stays_one_literal(spec) -> None:
    """@verifies REQ-1501"""
    hostile = "x' OR '1'='1"
    rendered = render_query(
        spec.query or "",
        entity=EntityInfo(id=hostile, domain_name="it-energy-community"),
        params=_params(spec),
    )
    assert "community_id = 'x'' OR ''1''=''1'" in rendered
    assert "community_id = 'x' OR" not in rendered


def test_fetchers_without_a_rec_table_are_not_scoped() -> None:
    """@verifies REQ-1502"""
    specs = _community_specs()
    others = [s for s in specs.values() if not REC_TABLE.search(s.query or "")]
    assert {"weather_current", "pv_potential_forecast", "boundary_shape"} <= {s.id for s in others}
    for spec in others:
        assert "community_id" not in (spec.query or ""), spec.id


def _total_forecast():
    return next(s for s in ITParticipantDomain().get_value_specs() if s.id == "total_meters_forecast")


def test_the_member_forecast_is_the_members_community() -> None:
    """@verifies REQ-1405"""
    spec = _total_forecast()
    entity = EntityInfo(
        id="sub-1", domain_name="it-participant", metadata={"community_key": "example-rec"}
    )
    rendered = render_query(spec.query or "", entity=entity, params=_params(spec))
    assert "community_id = 'example-rec'" in rendered


@pytest.mark.parametrize("metadata", [{"community_key": None}, {}], ids=["none", "absent"])
def test_a_member_with_no_community_reads_no_forecast(metadata) -> None:
    """@verifies REQ-1405"""
    spec = _total_forecast()
    entity = EntityInfo(id="sub-1", domain_name="it-participant", metadata=metadata)
    rendered = render_query(spec.query or "", entity=entity, params=_params(spec))
    assert "community_id = NULL" in rendered
