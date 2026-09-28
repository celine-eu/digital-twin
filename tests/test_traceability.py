# tests/test_traceability.py
"""
Holds the requirement universe and the test suite to each other.

`docs/specifications/` states what the service must do; a test declares what it covers
with a `@verifies REQ-####` tag. The mapping between the two is **generated** — here,
by reading both sides — and never written down. A hand-maintained matrix is stale
within a week, which is why the tag lives next to the assertion instead.

Two directions, and both matter:

* a requirement nobody verifies is a gap, not a formatting slip;
* a tag naming a requirement that does not exist means a renumbering broke the trace
  silently.

A requirement marked `**Status:** planned` (ADR-0002) is written ahead of its code: it
is exempt from the first check, and a tag naming it is a failure, because the change
that lands its tests removes the status line.

`.agents/harness.toml` names `provider = "harness"`, so the harness checker owns the
matrix proper. This module is the guard that runs in the ordinary suite, because that
checker is not installed in every checkout.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPECS = REPO / "docs" / "specifications"
TESTS = REPO / "tests"

# A requirement is *defined* by a heading naming it. Bare mentions in prose — "(see
# REQ-1103)" — are references and must not create a requirement.
#
# Headings rather than bold leads since 2026-08-15: the agent harness reads requirements
# from markdown headings, and while these were bold paragraph leads it found none — which
# made every `@verifies` tag here name a requirement it believed did not exist.
DEFINITION = re.compile(r"^#{1,6}\s+(REQ-\d{4})\b", re.MULTILINE)

VERIFIES = re.compile(r"@verifies\s+((?:REQ-\d{4}[,\s]*)+)")
REQ_ID = re.compile(r"REQ-\d{4}")

# ADR-0002: a requirement may land ahead of the code, marked by a status line directly
# under its heading. The only status is `planned`; no line means implemented.
HEADING = re.compile(r"^#{1,6}\s", re.MULTILINE)
STATUS = re.compile(r"^\*\*Status:\*\*\s*(.*?)\s*$", re.MULTILINE)
PLANNED = "planned"


def _defined() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted(SPECS.glob("*.md")):
        for req in DEFINITION.findall(path.read_text()):
            found[req] = path
    return found


def _statuses() -> dict[str, str]:
    """The status line of every requirement that has one.

    A requirement's section runs from its heading to the next heading of any level, and
    the status line is the first non-blank line of it.
    """
    statuses: dict[str, str] = {}
    for path in sorted(SPECS.glob("*.md")):
        text = path.read_text()
        for match in DEFINITION.finditer(text):
            eol = text.find("\n", match.end())
            start = len(text) if eol == -1 else eol + 1
            following = HEADING.search(text, start)
            body = text[start:following.start() if following else len(text)].lstrip("\n")
            first = body.split("\n", 1)[0]
            status = STATUS.match(first)
            if status:
                statuses[match.group(1)] = status.group(1)
    return statuses


def _planned() -> set[str]:
    return {req for req, status in _statuses().items() if status == PLANNED}


def _tagged() -> dict[str, list[str]]:
    tags: dict[str, list[str]] = {}
    for path in sorted(TESTS.rglob("*.py")):
        text = path.read_text()
        for block in VERIFIES.findall(text):
            for req in REQ_ID.findall(block):
                tags.setdefault(req, []).append(path.name)
    return tags


def test_specifications_directory_exists():
    assert SPECS.is_dir(), "docs/specifications/ is where requirements live"


def test_some_requirements_are_defined():
    """Guards the parser: a regex that silently matched nothing would make every
    assertion below vacuously true."""
    assert _defined()


def test_every_requirement_is_verified():
    """A planned requirement (ADR-0002) is exempt: nothing is meant to verify it yet."""
    defined = _defined()
    tagged = _tagged()
    planned = _planned()
    unverified = sorted(req for req in defined if req not in tagged and req not in planned)
    assert not unverified, (
        "requirements with no @verifies tag:\n"
        + "\n".join(f"  {req}  ({defined[req].name})" for req in unverified)
    )


def test_every_tag_names_a_real_requirement():
    defined = _defined()
    tagged = _tagged()
    unknown = sorted(req for req in tagged if req not in defined)
    assert not unknown, (
        "@verifies tags naming requirements that do not exist:\n"
        + "\n".join(f"  {req}  (in {', '.join(sorted(set(tagged[req])))})" for req in unknown)
    )


def test_no_tag_names_a_planned_requirement():
    """ADR-0002: the change that lands a requirement's tests removes its status line.

    A tag on a planned requirement means one of the two was forgotten, and the
    specifications then under-report what the suite verifies.
    """
    planned = _planned()
    tagged = _tagged()
    early = sorted(req for req in tagged if req in planned)
    assert not early, (
        "@verifies tags naming requirements still marked planned:\n"
        + "\n".join(f"  {req}  (in {', '.join(sorted(set(tagged[req])))})" for req in early)
    )


def test_the_only_status_is_planned():
    """A misspelt status must not quietly exempt a requirement from coverage, nor
    quietly subject it: either reading would be a status nobody chose."""
    unknown = sorted(f"{req}: {status!r}" for req, status in _statuses().items() if status != PLANNED)
    assert not unknown, f"status lines other than {PLANNED!r}: {unknown}"


def test_status_parser_sees_the_planned_requirements():
    """Guards the parser the way `test_some_requirements_are_defined` does: every
    `**Status:**` line in the specifications must belong to some requirement."""
    lines = sum(len(STATUS.findall(p.read_text())) for p in SPECS.glob("*.md"))
    assert lines == len(_statuses()), (
        "a **Status:** line is not directly under a requirement heading"
    )


def test_identifiers_do_not_collide_with_harness_rule_ids():
    """This repository allocates from REQ-1000 up.

    The standard files cite the harness's own rule ids — REQ-0003, REQ-0012, REQ-0303 —
    in the same four-digit form. Numbering below 1000 here would make one identifier
    mean two different things in one repository.
    """
    low = sorted(req for req in _defined() if int(req.removeprefix("REQ-")) < 1000)
    assert not low, f"requirements numbered below REQ-1000: {low}"


def test_requirements_are_not_defined_twice():
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for path in sorted(SPECS.glob("*.md")):
        for req in DEFINITION.findall(path.read_text()):
            if req in seen and seen[req] != path.name:
                duplicates.append(f"{req} in {seen[req]} and {path.name}")
            seen[req] = path.name
    assert not duplicates, duplicates
