"""Fair gamification fetchers (rec_fair_* gold tables) on the participant domain.

Spec: demo3 docs/superpowers/specs/2026-10-07-gamification-equa-concept.md (design 2026-10-09),
plan Task 3.1. Every fetcher is device-scoped (REQ-1402 ownership check keys on ``device_id``)
and reads only the fair gold tables.
"""

import re

import pytest

from celine.dt.domains.participant.domain import ITParticipantDomain

FAIR_IDS = {
    "rec_fair_season_board": 1,
    "rec_fair_weekly_scores": 12,
    "rec_fair_device_class": 1,
    "rec_fair_commitment_outcomes": 100,
}


@pytest.fixture(scope="module")
def specs():
    return {s.id: s for s in ITParticipantDomain().get_value_specs()}


@pytest.mark.parametrize("fetcher_id,limit", sorted(FAIR_IDS.items()))
def test_fair_fetcher_exists_with_expected_limit(specs, fetcher_id, limit):
    assert fetcher_id in specs, f"missing fetcher {fetcher_id}"
    assert specs[fetcher_id].limit == limit


@pytest.mark.parametrize("fetcher_id", sorted(FAIR_IDS))
def test_fair_fetcher_requires_device_id_only(specs, fetcher_id):
    schema = specs[fetcher_id].payload_schema
    assert schema["required"] == ["device_id"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"device_id"}


@pytest.mark.parametrize("fetcher_id", sorted(FAIR_IDS))
def test_fair_fetcher_reads_only_fair_tables_and_filters_by_device(specs, fetcher_id):
    sql = specs[fetcher_id].query
    tables = re.findall(r"FROM\s+([\w.]+)", sql, flags=re.IGNORECASE)
    assert tables and all(t.startswith("ds_dev_gold.rec_fair_") for t in tables), tables
    assert "device_id = :device_id" in sql
    assert specs[fetcher_id].client == "dataset_api"


def test_season_board_is_the_current_season_with_all_board_columns(specs):
    sql = specs["rec_fair_season_board"].query
    assert "is_current_season" in sql
    for col in ("virtuosi_rank", "growth_rank", "general_rank", "total_ranked_virtuosi", "total_ranked_growth",
                "total_ranked_general", "rank_reason", "required_weeks", "elapsed_weeks", "valid_weeks", "season_points",
                "mean_level", "mean_growth", "actions_sum", "weeks_at_100", "category", "pv_class", "season_end"):
        assert col in sql, col


def test_weekly_scores_are_newest_first_with_reason_codes_and_explanation_numbers(specs):
    sql = specs["rec_fair_weekly_scores"].query
    assert "ORDER BY week_start DESC" in sql
    for col in ("level_points", "level_reason", "growth_points", "growth_reason", "actions_points", "actions_reason",
                "weekly_points", "flag_import_rise", "night_share", "level_pct", "ref_group_n", "ref_group_effective",
                "cloudy_valid_days", "growth_delta_adj", "kept_count", "surplus_hours", "is_valid_week"):
        assert col in sql, col


def test_commitment_outcomes_cover_the_last_90_days(specs):
    sql = specs["rec_fair_commitment_outcomes"].query
    assert "90 days" in sql
    for col in ("commitment_id", "matched", "is_kept", "points", "surplus_points", "reason", "period_start", "period_end"):
        assert col in sql, col
