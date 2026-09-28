# ADR-0002 — A requirement may land ahead of the code, marked planned

**Date:** 2026-09-27
**Status:** accepted

## Context

ADR-0001 made the requirement universe and the suite answer to each other:
`tests/test_traceability.py` fails when a requirement has no verifying tag. Every
requirement written since was a statement about code that already existed, so the rule
never cost anything.

It has no answer for a change that crosses a seam. The next platform change needs two new
value fetchers here — a boundary lookup by point and a boundary shape lookup by id — and
their consumers, onboarding and the community dashboard's backend, are specified and built
in the same delivery against them. If a requirement may only be written once the code
exists, the consumers are designed against nothing, and this repository's half of the
contract is whatever the first implementation happened to do. Writing the requirement first
under ADR-0001 as it stands turns the suite red until the code lands.

The registry and the SDK meet the same question for their own requirements and answer it the
same way (their decisions on planned requirements). Repositories on either side of one seam
with different rules would leave the seam half-specified.

## Decision

A requirement may be written before the code that satisfies it, provided it is **marked
planned**:

- A line `**Status:** planned` directly under its heading. A requirement with no status line
  is implemented, which is every requirement written before this decision.
- A planned requirement states the behaviour the change will deliver, in the same terms as an
  implemented one: something a test can name.
- No test carries `@verifies` for it yet. The change that makes it true lands its tests with
  their tags and **removes the status line in the same change**.
- An implemented requirement is never rewritten to describe behaviour the code lacks. When
  planned work changes it, the planned behaviour is a new planned requirement, and the current
  text stays true until the change lands.

`tests/test_traceability.py` measures this: a planned requirement is exempt from the
"no verifying tag" check; a tag naming a planned requirement fails, because the status line
should have gone with the test that tagged it; and a status line saying anything other than
`planned` fails, so a typo cannot quietly exempt a requirement.

This extends ADR-0001; it supersedes nothing in it. The numbering and the provider stand.

## Consequences

- The specifications now hold two kinds of sentence, and a reader must check the status line
  before relying on one. A planned requirement is a design commitment, not something a caller
  may use.
- The harness checker (`python -m harness .`) does not read the status line, and reports a
  planned requirement as uncovered until its tests land. That is the honest reading: nothing
  verifies it. The guard test in the ordinary suite is the one that knows the difference.
- A planned requirement should not sit in the specifications long. One that outlives the
  delivery it was written for is an aspiration, and is either landed or deleted.
- **What will tempt someone to undo it:** a planned requirement nobody lands, making the
  specifications read as if they promised more than the service does. The answer is the rule
  above — landed or deleted — not the removal of the status line from the vocabulary.
