# Specifications

**What the Digital Twin service must do.** Everything here is a requirement: a statement
about behaviour that a test can be pointed at.

The rest of `docs/` describes and teaches. This directory constrains. Where a description
elsewhere disagrees with a requirement here, the requirement is the one that was checked.

## The documents

| Document | Covers |
|---|---|
| [runtime.md](runtime.md) | domain registration, route mounting, entity resolution, discovery |
| [values.md](values.md) | value fetcher registration, execution, validation, pagination |
| [query-templates.md](query-templates.md) | the two rendering phases and the boundary between them |

## Identifiers

Requirements are numbered `REQ-####`, the harness default.

Numbers are allocated in blocks from **REQ-1000 upward**, and a retired requirement's
number is never reused:

| Block | Subject |
|---|---|
| `REQ-10xx` | runtime: registration, routing, entity resolution, discovery |
| `REQ-11xx` | values |
| `REQ-12xx` | query templates |

Starting at 1000 is not arbitrary. `AGENTS.md` and `.agents/README.md` are issued by the
agent harness and cite its *own* rule identifiers in the same four-digit form — REQ-0003
for the closed directory set, REQ-0012 for an altered standard file, REQ-0303 for a home
path in committed material. Those constrain this repository's structure; the ones here
constrain the service. Keeping this repository's block above them means one number never
means two things.

## How a requirement is verified

A test declares what it covers with a `@verifies` tag in its docstring or in a comment
directly above it:

```python
def test_entity_resolution_reject(self):
    """@verifies REQ-1031"""
    ...
```

The mapping from requirement to test is **generated from these tags**, never written down.
A hand-maintained matrix is stale within a week, which is the whole reason the tag lives
next to the assertion instead.

Two consequences worth stating, because both are easy to get wrong:

- **A requirement with no tag is unverified**, and that is a finding rather than a
  formatting slip. `tests/test_traceability.py` fails on it.
- **A tag naming a requirement that does not exist** is also a failure. Renumbering a
  requirement without moving its tags breaks the trace silently otherwise.

`tests/test_traceability.py` enforces both directions in the ordinary suite, so the answer
to "is this verified?" is available from `uv run pytest` alone — the harness checker
(`python -m harness .`) is not installed in every checkout.

## Writing one

- **State behaviour, not implementation.** "An unknown fetcher id answers 404", not
  "`fetch_values_get` catches `KeyError`". The implementation is free to move; the
  requirement is what must survive the move.
- **One testable claim per requirement.** If a statement needs "and" to hold two
  independent behaviours, it is two requirements.
- **MUST is the only modal.** A requirement that something *should* happen cannot fail.
- **If it cannot be tested, it is not a requirement** — it is a description, and belongs in
  the document that describes.
