# A value fetcher query is rendered twice, and mixing the two phases is how you get hurt

A `ValueFetcherSpec.query` looks like one SQL template. It is rendered in **two separate
phases**, and which phase a piece of the query belongs to is not visible from the syntax.

## The two phases

1. **Jinja2, for structure.** Conditional clauses, joins, table names, anything that
   changes the *shape* of the statement: `{% if risk_vector %}`, `{{ entity.id }}`.
2. **Bind parameters, for values.** Anything a caller supplied: `:date_from`, `:date_to`.
   These are quoted by the driver, not by the template.

The rule that follows is the whole point: **a user-supplied scalar must never reach phase
one.** Interpolating it with `{{ }}` puts caller data into the statement's structure, which
is SQL injection with extra steps. Entity context (`{{ entity.id }}`,
`{{ entity.metadata.zone }}`) is safe because it comes from `resolve_entity`, not from the
request body.

Two filters exist for the cases where structure and values genuinely meet:

- `sql_list` — a list into an `IN` clause: `{{ values | sql_list }}` renders `('a','b','c')`
- `sql_quote` — a single value into an escaped literal

## The trap

**PostgreSQL casts survive the bind-parameter pass.** `::date` and `::text` look exactly
like a bind parameter to a naive scanner — `:date` is right there inside `::date`. The
parameter regex uses a negative lookbehind to skip a doubled colon, which is why casts work
at all.

So a cast is safe, and it is safe *because of a lookbehind in a regex*, not because
anything about the syntax makes it obviously distinguishable. If that regex is ever
rewritten, every cast in every domain breaks at once and the failure surfaces as an
unrelated-looking bind error.

Where it lives: the renderer is `src/celine/dt/core/values/template.py`, and the spec it
serves is `src/celine/dt/contracts/values.py`.

## What to do with it

- Structural SQL → Jinja2. Caller-supplied scalars → bind parameters. Never the reverse.
- Lists for `IN` → `sql_list`, not string joining.
- When adding a cast, use `::`; a single-colon cast is not a cast, it is a parameter that
  will not bind.
- When touching the renderer, the casts are the regression to test for. They are the case
  that looks like the thing it must not match.
