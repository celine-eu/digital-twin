# celine/dt/core/values/executor.py
"""
Value fetch execution engine.

Handles payload validation, Jinja-based query rendering with entity
context injection, client query execution, and optional output mapping.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import jsonschema

from celine.dt.contracts.entity import EntityInfo
from celine.dt.contracts.values import ValueFetcherSpec
from celine.dt.core.values.template import render_query

if TYPE_CHECKING:
    from celine.dt.api.context import Ctx


logger = logging.getLogger(__name__)


class ValidationError(ValueError):
    """Raised when payload validation against JSON Schema fails."""

    def __init__(self, message: str, errors: list[str] | None = None):
        self.message = message
        self.errors = errors or []
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "validation_error",
            "message": self.message,
            "errors": self.errors,
        }

    def __str__(self) -> str:
        return self.message


class FetchRefused(PermissionError):
    """A domain refused this fetch for this caller (REQ-1116).

    Raised by ``DTDomain.check_fetch`` before the statement is rendered or sent. The
    values and ontology routes answer it 403; ``reason`` is the short code the access
    audit records (REQ-1081).
    """

    def __init__(self, reason: str, message: str = "Not permitted for this caller"):
        self.reason = reason
        self.message = message
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {"error": "forbidden", "reason": self.reason, "message": self.message}


class CallerIdentityRequired(PermissionError):
    """A ``"caller"`` fetcher was fetched with no caller to fetch for (REQ-1133).

    Raised before the statement is rendered or sent, when the fetch carries no request
    context and neither the fetcher's spec
    (``identity="service"``) nor the call (``as_service=True``) declares the Digital
    Twin's own identity. The client would otherwise fall back to the service token and
    read every row the Digital Twin may read.
    """

    code = "caller_identity_required"

    def __init__(self, fetcher_id: str) -> None:
        self.fetcher_id = fetcher_id
        self.message = (
            f"Fetcher '{fetcher_id}' reads with the caller's identity and no caller is "
            "known; a fetch outside a request must pass as_service=True"
        )
        super().__init__(self.message)

    def to_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message}


@dataclass
class FetchResult:
    """Result of a value fetch operation."""

    items: list[dict[str, Any]]
    limit: int
    offset: int
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "limit": self.limit,
            "offset": self.offset,
            "count": self.count,
        }


@dataclass
class FetcherDescriptor:
    """Resolved fetcher: spec + live client + optional mapper."""

    spec: ValueFetcherSpec
    client: Any
    output_mapper: Any | None = None

    @property
    def id(self) -> str:
        return self.spec.id


def resolve_output_mapper(path: str | None) -> Any | None:
    """Resolve a spec's ``output_mapper`` (``module:attr``) to an object with ``.map(row)``.

    A class is instantiated with no arguments; any other attribute is used as is.
    Called at registration, so a bad path fails startup rather than a request.
    """
    if not path:
        return None
    from celine.dt.core.loader import import_attr

    target = import_attr(path)
    mapper = target() if isinstance(target, type) else target
    if not callable(getattr(mapper, "map", None)):
        raise TypeError(f"Output mapper '{path}' has no callable 'map(row)'")
    return mapper


def _non_finite_path(value: Any, path: str = "") -> str | None:
    """The ``/``-joined path of the first NaN or infinite number in ``value``, if any."""
    if isinstance(value, float) and not math.isfinite(value):
        return path
    if isinstance(value, dict):
        items = value.items()
    elif isinstance(value, (list, tuple)):
        items = enumerate(value)
    else:
        return None
    for key, item in items:
        found = _non_finite_path(item, f"{path}/{key}" if path else str(key))
        if found is not None:
            return found
    return None


class ValuesFetcher:
    """Stateless executor for value fetch operations."""

    def validate_payload(
        self,
        payload: dict[str, Any],
        descriptor: FetcherDescriptor,
    ) -> dict[str, Any]:
        schema = descriptor.spec.payload_schema
        if schema is None:
            return payload

        # Apply defaults
        properties = schema.get("properties", {})
        enriched = dict(payload)
        for prop_name, prop_schema in properties.items():
            if prop_name not in enriched and "default" in prop_schema:
                enriched[prop_name] = prop_schema["default"]

        try:
            jsonschema.validate(enriched, schema)
        except jsonschema.ValidationError as exc:
            # The message quotes the offending value, which may be a coordinate or
            # some other personal datum; the log names only where and which rule.
            # The caller still gets the full message in the 400.
            logger.warning(
                "Payload validation failed for '%s': property %s failed '%s'",
                descriptor.id,
                "/".join(str(p) for p in exc.absolute_path) or "(root)",
                exc.validator,
            )
            raise ValidationError(
                f"Payload validation failed: {exc.message}",
                errors=[exc.message],
            ) from exc

        # JSON Schema's "number" admits NaN, and NaN passes every minimum/maximum, so
        # the schema alone lets it through to a statement with no literal for it
        # (REQ-1115). The value is not echoed: it may sit beside personal data.
        path = _non_finite_path(enriched)
        if path is not None:
            logger.warning(
                "Payload validation failed for '%s': property %s is not a finite number",
                descriptor.id,
                path or "(root)",
            )
            raise ValidationError(
                f"Payload validation failed: {path or '(root)'} is not a finite number",
                errors=[f"{path or '(root)'} is not a finite number"],
            )

        return enriched

    async def fetch(
        self,
        descriptor: FetcherDescriptor,
        payload: dict[str, Any],
        *,
        entity: EntityInfo | None = None,
        limit: int | None = None,
        offset: int | None = None,
        ctx: Ctx | None,
        as_service: bool = False,
    ) -> FetchResult:
        """Execute a value fetch with Jinja template rendering.

        Args:
            descriptor: Resolved fetcher descriptor.
            payload: User-supplied parameters.
            entity: Entity context for Jinja templates.
            limit: Override default limit.
            offset: Override default offset.
            ctx: The request context; its token is the caller's identity.
            as_service: Read with the Digital Twin's own identity for this call,
                whatever the spec declares. For work outside a request (an event
                handler); without it a ``"caller"`` fetcher needs a caller (REQ-1133).

        Returns:
            ``FetchResult`` with items and pagination metadata.
        """
        spec = descriptor.spec
        service_identity = as_service or spec.identity == "service"

        # REQ-1133: a "caller" fetcher with no request context fails closed. Without
        # one the client would authenticate with the service token, and dataset-api
        # would apply no caller's row filter.
        if not service_identity and ctx is None:
            logger.warning(
                "Fetch refused: code=%s fetcher=%s", CallerIdentityRequired.code, spec.id
            )
            raise CallerIdentityRequired(spec.id)

        effective_limit = limit if limit is not None else spec.limit
        effective_offset = offset if offset is not None else spec.offset

        validated = self.validate_payload(payload, descriptor)

        # REQ-1116: the domain serving the request may refuse the validated payload
        # for this caller. A context without a domain (an event handler's) has no
        # caller to refuse.
        domain = getattr(ctx, "domain", None)
        if domain is not None:
            await domain.check_fetch(spec, validated, ctx)

        # Render query with Jinja + bind params
        query: str | None = None
        if spec.query:
            try:
                query = render_query(spec.query, entity=entity, params=validated)
            except ValueError:
                logger.exception("Query rendering failed for fetcher '%s'", spec.id)
                raise

        # REQ-1127: the rendered statement carries the payload's literals (for
        # boundary_at_point, a supply address's coordinates), so it is never logged.
        logger.debug(
            "Fetcher '%s': limit=%d offset=%d",
            spec.id,
            effective_limit,
            effective_offset,
        )

        # REQ-1121 / REQ-1125: the caller's context, and with it the caller's token,
        # goes to the client unless the fetcher reads open reference data under the
        # Digital Twin's own identity. Without a context the client authenticates with
        # its service token provider. The caller was already authenticated by the route.
        # REQ-1133: or the call itself declares the service identity.
        client_ctx = None if service_identity else ctx

        try:
            items = await descriptor.client.query(
                sql=query or "",
                limit=effective_limit,
                offset=effective_offset,
                ctx=client_ctx,
            )
        except Exception:
            logger.error("Client query failed for fetcher '%s'", spec.id)
            raise

        if descriptor.output_mapper:
            try:
                items = [descriptor.output_mapper.map(item) for item in items]
            except Exception:
                logger.exception("Output mapping failed for fetcher '%s'", spec.id)
                raise

        return FetchResult(
            items=items,
            limit=effective_limit,
            offset=effective_offset,
            count=len(items),
        )
