# tests/test_weather_fetchers.py
"""
The weather fetchers answer in the field names the AI assistant reads.

`celine-ai-assistant`'s weather skill reads `humidity`, `uvi`, `sunrise` and
`sunset` from `weather_current`, and `uvi`, `sunrise` and `sunset` from
`weather_daily`. A name missing here is not an error anywhere: the assistant
just reports the value as absent. No query is executed.
"""
from __future__ import annotations

import re

import pytest

from celine.dt.domains.energy_community.domain import domain


def _output_names(fetcher_id: str) -> set[str]:
    """The column names a fetcher's SELECT list produces (alias, else column)."""
    spec = next(s for s in domain.get_value_specs() if s.id == fetcher_id)
    select_list = re.search(r"select(.*?)\bfrom\b", spec.query, re.IGNORECASE | re.DOTALL).group(1)
    names = set()
    for item in select_list.split(","):
        words = item.split()
        if words:
            names.add(words[-1].lower())
    return names


@pytest.mark.parametrize("name", ["humidity", "uvi", "sunrise", "sunset"])
def test_current_weather_answers_what_the_assistant_reads(name: str) -> None:
    assert name in _output_names("weather_current")


@pytest.mark.parametrize("name", ["uvi", "sunrise", "sunset"])
def test_daily_weather_answers_what_the_assistant_reads(name: str) -> None:
    assert name in _output_names("weather_daily")


@pytest.mark.parametrize(
    "fetcher_id",
    [s.id for s in domain.get_value_specs() if s.id.startswith("weather_")],
)
def test_weather_fetchers_read_gold_only(fetcher_id: str) -> None:
    """dataset-api exposes no layer below gold (gold-only rule, 2026-09-20): a
    silver table answers 403 to every caller, whatever the query."""
    spec = next(s for s in domain.get_value_specs() if s.id == fetcher_id)
    assert "ds_dev_silver." not in spec.query
