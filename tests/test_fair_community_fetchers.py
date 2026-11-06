"""Fair gamification fetchers on the community side (plan Tasks 3.2 / 6.2).

* ``rec_fair_season_boards_community`` (manager-gated): the ranked standings of a community,
  device-keyed, no personal data.
* ``rec_fair_commitment_outcome`` (community domain): one commitment's fair outcome, looked up
  by device and period by the flexibility-api when it settles a window.
"""

import re

import pytest

from celine.dt.domains.energy_community.domain import ITEnergyCommunityDomain
from celine.dt.domains.energy_community.manager_fetchers import manager_value_specs


@pytest.fixture(scope="module")
def manager_specs():
    return {s.id: s for s in manager_value_specs()}


@pytest.fixture(scope="module")
def community_specs():
    return {s.id: s for s in ITEnergyCommunityDomain().get_value_specs()}


def test_season_boards_community_is_scoped_to_the_entity_and_ranked_only(manager_specs):
    spec = manager_specs["rec_fair_season_boards_community"]
    sql = spec.query
    assert "{{ entity.id | sql_quote }}" in sql
    assert "FROM ds_dev_gold.rec_fair_season_boards" in sql
    assert "is_ranked" in sql
    assert ":start" in sql and ":end" in sql  # seasons overlapping the console's period
    assert sorted(spec.payload_schema["required"]) == ["end", "start"]
    assert spec.limit == 500
    for col in ("device_id", "category", "virtuosi_rank", "growth_rank", "general_rank", "general_score", "season_points"):
        assert col in sql, col
    assert "user_id" not in sql.lower() and "email" not in sql.lower()


def test_commitment_outcome_is_looked_up_by_device_and_period(community_specs):
    spec = community_specs["rec_fair_commitment_outcome"]
    sql = spec.query
    assert "FROM ds_dev_gold.rec_fair_commitment_outcomes" in sql
    assert "{{ entity.id | sql_quote }}" in sql
    assert "device_id = :device_id" in sql and ":period_start" in sql and ":period_end" in sql
    assert spec.limit == 1
    assert sorted(spec.payload_schema["required"]) == ["device_id", "period_end", "period_start"]
    assert spec.payload_schema["additionalProperties"] is False
    for col in ("commitment_id", "is_kept", "points", "surplus_points", "reason"):
        assert re.search(rf"\b{col}\b", sql), col
