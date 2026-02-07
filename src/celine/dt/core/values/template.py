# celine/dt/core/values/template.py
"""
Jinja2-based query template engine.

Structural template logic (conditional clauses, entity context injection)
is handled by Jinja. Bind-parameter values still use ``:param_name``
syntax for safe SQL injection via the underlying client.
"""
from __future__ import annotations

import logging
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

# Bind-parameter pattern (passed through to the client, not Jinja)
BIND_PARAM_PATTERN = re.compile(r":(\w+)")


# Custom Jinja filter: turn a Python list into SQL ``(v1, v2, v3)``
def _sql_list_filter(value: Any) -> str:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"sql_list expects a list, got {type(value).__name__}")
    quoted = ", ".join(f"'{v}'" if isinstance(v, str) else str(v) for v in value)
    return f"({quoted})"


def _sql_quote_filter(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
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

    After Jinja rendering, ``:param_name`` bind parameters are substituted
    with safely quoted values from ``params``.

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

    # Phase 2: bind-parameter substitution
    def _replacer(match: re.Match) -> str:
        name = match.group(1)
        if name not in params:
            raise ValueError(f"Bind parameter ':{name}' not provided in payload")
        return _sql_quote_filter(params[name])

    try:
        result = BIND_PARAM_PATTERN.sub(_replacer, rendered)
    except ValueError:
        logger.error("Bind parameter substitution failed for query")
        raise

    return result
