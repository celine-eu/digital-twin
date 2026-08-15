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

# A requirement is *defined* by a bold identifier opening a line. Bare mentions in prose
# — "(see REQ-1103)" — are references and must not create a requirement.
DEFINITION = re.compile(r"^\*\*(REQ-\d{4})\*\*", re.MULTILINE)

VERIFIES = re.compile(r"@verifies\s+((?:REQ-\d{4}[,\s]*)+)")
REQ_ID = re.compile(r"REQ-\d{4}")


def _defined() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted(SPECS.glob("*.md")):
        for req in DEFINITION.findall(path.read_text()):
            found[req] = path
    return found


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
    defined = _defined()
    tagged = _tagged()
    unverified = sorted(req for req in defined if req not in tagged)
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
