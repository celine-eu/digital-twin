from celine.dt.domains.energy_community.manager_fetchers import manager_value_specs


def test_manager_fetchers_are_device_keyed_or_aggregated() -> None:
    specs = manager_value_specs()

    assert {spec.id for spec in specs} == {
        "rec_population_summary",
        "rec_meters_health_summary",
        "rec_meters_missing_intervals",
        "rec_device_streaks",
        "rec_points_leaderboard_community",
        "rec_points_distribution",
        "rec_device_points_ledger",
        "rec_flexibility_windows_history",
        "rec_flexibility_chain_daily",
    }
    for spec in specs:
        query = (spec.query or "").lower()
        assert "participant_id" not in query
        assert "email" not in query
        assert "address" not in query
