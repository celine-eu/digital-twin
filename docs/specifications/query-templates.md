# Specification — query templates

A fetcher's `query` is one string that is rendered **twice**. These requirements fix the
boundary between the two passes, because nothing in the syntax marks it.

The trap, and why it is a trap, is `.agents/knowledge/query-templates-are-two-phase.md`.
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
