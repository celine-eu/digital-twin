# ADR-0001 — This repository owns its traceability, and numbers requirements from REQ-1000

**Date:** 2026-08-15
**Status:** accepted

## Context

Until 2026-08-15 this repository had no requirements. `.agents/harness.toml` named no
traceability provider, no requirement identifiers existed, and `.agents/playbooks/testing.md`
recorded that state explicitly. "Is this behaviour verified?" had no answer beyond reading
the suite — and the suite itself was not running, so it had no answer at all.

Adding requirements forced two choices.

**Who answers the question.** The harness offers two providers. `external` delegates to a
tool the repository already has, and reports those requirements as DELEGATED. `harness`
means the checker derives the matrix from `docs/specifications/` and `@verifies` tags.
There was no existing tool to delegate to: no conformance target, no requirement universe,
no evidence syntax. Delegation would have named a tool that did not exist.

**Which numbers.** The harness's default pattern is `REQ-[0-9]{4}`. But `AGENTS.md` and
`.agents/README.md` — both issued by the harness, both present in this repository — cite
the harness's *own* rule identifiers in exactly that form: REQ-0003 for the closed
directory set, REQ-0012 for an altered standard file, REQ-0102 for a missing work
directory, REQ-0303 for a home path in committed material. Those constrain this
repository's structure. Requirements written here constrain the Digital Twin service. Under
one pattern starting at 0001, the two collide: REQ-0012 would mean both "a standard file
has been altered" and whatever the twelfth service requirement happened to be.

A custom pattern (`REQ-DT-####`) was considered and rejected: it diverges from the standard
form for no benefit that a disjoint number range does not also provide, and every tool,
reader and future harness upgrade then has to know about the local variant.

## Decision

Declare `provider = "harness"` in `.agents/harness.toml`. Requirements live in
`docs/specifications/`, carry `REQ-####` identifiers in the harness's default form, and are
verified by `@verifies REQ-####` tags placed next to the assertions.

**Allocate this repository's numbers from REQ-1000 upward**, in blocks: `REQ-10xx` runtime,
`REQ-11xx` values, `REQ-12xx` query templates. The harness's own rule ids run in the low
hundreds and will not reach 1000.

Add `tests/test_traceability.py`, which fails when a requirement has no verifying tag and
when a tag names a requirement that does not exist.

## Consequences

The matrix is generated from the tags, never authored, so it cannot go stale the way a
hand-maintained table does. The cost is that a requirement is only as good as its tag: move
a test without its tag and the trace breaks — which is why the guard test exists and runs
in the ordinary suite rather than only under the harness checker, which is not installed in
every checkout.

`tests/test_traceability.py` is not a second traceability provider. It measures the same
universe the declaration names; it exists so the answer is available from `uv run pytest`
alone.

**What will tempt someone to undo it:** the number gap. `docs/specifications/` opening at
REQ-1001 looks like 1,000 missing requirements, and the tidy-minded instinct is to renumber
from 0001. Doing that reintroduces the collision this record exists to prevent, and
silently — nothing fails, two identifiers simply start meaning two things each. A
requirement's number is also never reused after retirement, so the sequence will develop
gaps anyway.
