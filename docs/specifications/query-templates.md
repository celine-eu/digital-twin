# Specification — query templates

A fetcher's `query` is one string that is rendered **twice**. These requirements fix the
boundary between the two passes, because nothing in the syntax marks it.

The trap, and why it is a trap, is in the companion's knowledge.
This document says only what must hold.

---

## The two phases

### REQ-1200 — A query MUST be rendered in two ordered passes: Jinja2 first, for structure; bind-parameter substitution second, for values.

### REQ-1201 — The Jinja2 pass MUST expose the resolved entity as `entity`, with its `id`, `domain_name` and `metadata`, and every validated payload property by name.

### REQ-1202 — A malformed template MUST fail as a `ValueError` naming the template error, not as a Jinja2 exception escaping the renderer.

---

## The boundary

### REQ-1210 — A caller-supplied scalar MUST reach the statement as a bind parameter, and MUST NOT be interpolated into the statement's structure.

> This is the whole point of the split. Interpolating a request value with `{{ }}` puts
> caller data into the *shape* of the statement, which is SQL injection with extra steps.
> `entity.*` is exempt: it comes from `resolve_entity`, not from the request body.

### REQ-1211 — Every fetcher this repository ships MUST satisfy REQ-1210.

A payload property interpolated with `{{ }}` MUST pass through `sql_list` or `sql_quote`.

### REQ-1212 — A bind-parameter value MUST be escaped for the statement, and MUST NOT be re-scanned as template syntax or as a further bind parameter.

> A value containing `{{ entity.id }}`, or a bare `:name`, must reach the database as that
> literal text. Substitution happens after rendering, precisely so it cannot recurse.

### REQ-1213 — Every `:param` in a shipped fetcher's query MUST be declared in that fetcher's `payload_schema`.

> An undeclared bind parameter cannot be supplied and cannot be defaulted, so the fetcher
> raises on every request — a 500 for something that can never succeed.

### REQ-1214 — A fetcher that reads one of several tables chosen by a payload value MUST choose it with a Jinja branch over the values of a closed enum, each branch naming its table literally in the template, and MUST NOT interpolate the payload value into the statement.

A value that matches no branch MUST fail rendering rather than fall through to a default
table.

> A table name is structure, so REQ-1210's bind parameter cannot carry it, and `sql_quote`
> renders a string literal, which is not a table name at all. The enum in the
> `payload_schema` (REQ-1110) refuses an unknown value first; the missing default is the
> second line, for the day the enum and the branches drift apart. The first user is the
> boundary fetchers' `source` (REQ-1150).

### REQ-1215 — Bind-parameter substitution MUST NOT substitute a `:name` that stands inside a single-quoted string literal or a double-quoted identifier of the Jinja-rendered text, and a rendered query with an unterminated quote MUST fail as a `ValueError`.

> REQ-1212 covers text a *bind parameter* brings in; this covers text the *Jinja pass*
> brings in. `sql_list` and `sql_quote` render caller values as literals before the second
> pass runs, so until 2026-09-27 an element such as `'x:ids'` had `:ids` substituted in the
> middle of its own literal: the inserted quotes closed it, and the rest of the caller's
> input became SQL. The second pass now reads the rendered text as PostgreSQL reads a
> standard literal (a doubled quote stays inside) and substitutes only outside literals.
> A template must therefore not write an `E'...'` literal, whose backslash escapes that
> reading does not follow.

---

## PostgreSQL casts

### REQ-1220 — A `::` cast MUST NOT be treated as a bind parameter.

> The bind-parameter pattern is `(?<!:):(\w+)`, and that negative lookbehind is the only
> thing separating `::date` from a parameter named `date`. It is the case that looks
> exactly like the thing it must not match.
>
> **This is the regression to guard.** Rewrite that expression without the lookbehind and
> every cast in every domain breaks at once, surfacing as an unrelated-looking bind error
> far from the change.

### REQ-1221 — REQ-1220 MUST hold even when the cast's type name is also a supplied payload property, and when a cast immediately follows a bind parameter (`:date_from::timestamp`).

---

## Filters

### REQ-1230 — `sql_list` MUST render a list as a parenthesised, comma-separated SQL list, quoting strings and leaving numbers unquoted.

### REQ-1231 — `sql_list` MUST reject a non-list argument rather than coerce it.

### REQ-1232 — `sql_quote` MUST escape embedded single quotes, and MUST render `None` as `NULL` and booleans as `TRUE`/`FALSE`.

### REQ-1233 — `sql_list` MUST escape an embedded single quote in a string element as `sql_quote` does.

> Until 2026-09-27 it wrapped each string in quotes and nothing more, so an element
> containing `'` ended the literal early. Each element is now rendered by `sql_quote` itself,
> so `None` and booleans render as there too. REQ-1230 stays true either way; this closes
> the gap beside it.

### REQ-1234 — `sql_list` MUST reject an empty list, failing as a `ValueError` naming the filter, rather than render `()`.

> `IN ()` is a syntax error in PostgreSQL. It reaches `dataset-api`, comes back a 400, and
> surfaces here as a 500 far from the template that produced it. What an empty list *means*
> is the fetcher's decision (REQ-1235), not the filter's.

### REQ-1235 — Every fetcher this repository ships that passes a list property to `sql_list` MUST either declare `minItems` of at least 1 for it or guard the filter with a Jinja branch that decides what an empty list answers.

> The optional filters already sit inside `{% if … %}`, and an empty list takes the else
> branch. A required list property with no `minItems` and no guard was the case that
> rendered `IN ()`: `it-grid.risks`' `dates`, which now declares `minItems: 1` (an empty list
> answers 400). `boundary_shape`'s `ids` is guarded instead, because an empty `ids` has an
> answer (REQ-1158). `tests/test_domain_specs.py` checks every shipped fetcher.

### REQ-1236 — `sql_quote` and `sql_list` MUST reject a NaN or infinite number, failing as a `ValueError`, rather than render it.

> `str()` renders `nan` and `inf`, which SQL reads as column names. REQ-1115 refuses such a
> value at the payload; this is the second line, for a value that reaches a filter another
> way.

---

## Undefined values

### REQ-1240 — An undefined value MUST be falsy in a conditional, so `{% if entity.metadata.x %}` takes the else branch rather than raising.

### REQ-1241 — An undefined value MUST raise when interpolated.

> The pair is the point: a guard that silently rendered the string "Undefined" into a
> statement would produce a query that runs and returns the wrong rows.

### REQ-1242 — A bind parameter absent from the payload MUST raise, naming the parameter.

---

## Renderability

### REQ-1250 — Every fetcher this repository ships MUST render under a payload supplying only its required properties and declared defaults, and MUST also render under a payload supplying every declared property.

> The two together take both branches of each `{% if optional %}`. A template that renders
> for one and not the other is a fetcher that 500s for half its callers, and the query is
> only a string until a request arrives.

### REQ-1251 — A rendered query MUST contain no unrendered template syntax and no unsubstituted bind parameter.
