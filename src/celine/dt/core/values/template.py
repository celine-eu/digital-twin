# celine/dt/core/values/template.py
"""
Jinja2-based query template engine.

Structural template logic (conditional clauses, entity context injection)
is handled by Jinja. Bind-parameter values still use ``:param_name``
syntax for safe SQL injection via the underlying client.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any

from jinja2 import (
    BaseLoader,
    Environment,
    TemplateSyntaxError,
    UndefinedError,
    Undefined,
)

from celine.dt.contracts.entity import EntityInfo

logger = logging.getLogger(__name__)

# Bind-parameter pattern (passed through to the client, not Jinja).
# Negative lookbehind skips PostgreSQL cast syntax (::text, ::date, etc.).
BIND_PARAM_PATTERN = re.compile(r"(?<!:):(\w+)")


# Custom Jinja filter: turn a Python list into SQL ``(v1, v2, v3)``
def _sql_list_filter(value: Any) -> str:
    """Render a non-empty list as a parenthesised SQL list.

    Each element is rendered exactly as ``sql_quote`` renders it, so an embedded
    single quote is doubled (REQ-1233). An empty list is refused (REQ-1234): ``()``
    is a syntax error in PostgreSQL, and what an empty list *means* is the
    fetcher's decision, taken in a Jinja branch around the filter (REQ-1235).
    """
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"sql_list expects a list, got {type(value).__name__}")
    if not value:
        raise ValueError(
            "sql_list got an empty list, which would render the invalid SQL '()'; "
            "guard the filter with a Jinja branch deciding what an empty list answers"
        )
    quoted = ", ".join(_sql_quote_filter(v) for v in value)
    return f"({quoted})"


def _sql_quote_filter(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and not math.isfinite(value):
        # str() would render nan/inf, which SQL reads as a column name (REQ-1236).
        raise ValueError("sql_quote got a non-finite number, which has no SQL literal")
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _create_jinja_env() -> Environment:
    env = Environment(
        loader=BaseLoader(),
        autoescape=False,
        keep_trailing_newline=True,
        undefined=_StrictishUndefined,
    )
    env.filters["sql_list"] = _sql_list_filter
    env.filters["sql_quote"] = _sql_quote_filter
    return env


class _StrictishUndefined(Undefined):
    """Jinja undefined that raises on attribute access but not on truthiness."""

    def __init__(self, name: str | None = None, **_: Any) -> None:
        self._name = name

    def __str__(self) -> str:
        raise UndefinedError(f"'{self._name}' is undefined in the template context")

    def __bool__(self) -> bool:
        return False

    def __getattr__(self, name: str) -> _StrictishUndefined:
        return _StrictishUndefined(name=f"{self._name}.{name}")


_jinja_env = _create_jinja_env()


def render_query(
    template_str: str,
    *,
    entity: EntityInfo | None = None,
    params: dict[str, Any] | None = None,
) -> str:
    """Render a Jinja2 query template.

    The template has access to:
    * ``entity`` – the resolved :class:`EntityInfo` (id, domain_name, metadata).
    * All keys in ``params``.

    After Jinja rendering, ``:param_name`` bind parameters outside quoted
    literals are substituted with safely quoted values from ``params``; a
    ``:name`` inside a literal is text (REQ-1215).

    Args:
        template_str: The raw Jinja2/SQL template.
        entity: The current entity info (may be ``None``).
        params: User-supplied query parameters.

    Returns:
        Fully rendered query string.
    """
    params = params or {}

    # Phase 1: Jinja structural rendering
    ctx: dict[str, Any] = {"entity": entity, **params}
    try:
        template = _jinja_env.from_string(template_str)
        rendered = template.render(ctx)
    except (TemplateSyntaxError, UndefinedError) as exc:
        logger.error("Jinja template rendering failed: %s", exc)
        raise ValueError(f"Query template error: {exc}") from exc

    # Phase 2: bind-parameter substitution, outside quoted literals only (REQ-1215)
    def _replacer(match: re.Match) -> str:
        name = match.group(1)
        if name not in params:
            raise ValueError(f"Bind parameter ':{name}' not provided in payload")
        return _sql_quote_filter(params[name])

    try:
        result = "".join(
            part if quoted else BIND_PARAM_PATTERN.sub(_replacer, part)
            for quoted, part in _split_quoted(rendered)
        )
    except ValueError:
        logger.error("Bind parameter substitution failed for query")
        raise

    return result


def _split_quoted(sql: str) -> list[tuple[bool, str]]:
    """Split rendered SQL into ``(is_quoted, text)`` runs.

    A quoted run is a single-quoted string literal or a double-quoted identifier,
    quotes included, with a doubled quote inside it read as an escaped quote, as
    PostgreSQL reads a standard literal. Phase 2 substitutes only in unquoted runs, so
    text that phase 1 put inside a literal (a ``sql_list``/``sql_quote`` rendering of a
    caller's value, say ``'x:ids'``) is never read as a bind parameter (REQ-1215).
    An unterminated quote raises: where the literal ends is then unknown, and so is
    what would be substituted.
    """
    runs: list[tuple[bool, str]] = []
    start = 0
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch not in ("'", '"'):
            i += 1
            continue
        if i > start:
            runs.append((False, sql[start:i]))
        j = i + 1
        while True:
            end = sql.find(ch, j)
            if end == -1:
                raise ValueError(f"Unterminated {ch} quote in rendered query")
            if end + 1 < n and sql[end + 1] == ch:
                j = end + 2  # doubled quote: still inside
                continue
            break
        runs.append((True, sql[i : end + 1]))
        i = start = end + 1
    if start < n:
        runs.append((False, sql[start:]))
    return runs
