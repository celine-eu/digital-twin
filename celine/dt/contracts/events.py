# celine/dt/contracts/events.py
"""
Base event contracts for Digital Twin computed events.

This module defines ONLY the base event envelope and generic app-level events.
Domain-specific events (like EV Charging) belong in their respective modules.

Events are designed to be:
- Self-describing (include @type and @context in serialized form)
- Traceable (include source, timestamp, correlation IDs)
- Extensible (payload is typed but allows domain-specific data)
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field, model_serializer


class EventSeverity(str, Enum):
    """Severity level for events that may indicate issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventSource(BaseModel):
    """
    Identifies the source of an event.

    Attributes:
        app_key: The DT app that generated the event.
        app_version: Version of the app.
        module: The module containing the app.
        instance_id: Unique identifier for this DT instance.
    """

    app_key: str = Field(..., description="DT app identifier")
    app_version: str = Field(..., description="App version")
    module: str | None = Field(default=None, description="Module name")
    instance_id: str | None = Field(default=None, description="DT instance ID")


T = TypeVar("T", bound=BaseModel)


class DTEvent(BaseModel, Generic[T]):
    """
    Base envelope for all Digital Twin events.

    This is the standard format for events published by DT apps.
    The payload contains the domain-specific computed result.

    When serialized to JSON, `event_type` becomes `@type` and
    `context` becomes `@context` for JSON-LD compatibility.

    Attributes:
        id: Unique event identifier.
        event_type: Event type URI (serializes as @type).
        context: JSON-LD context (serializes as @context).
        source: Information about the event producer.
        timestamp: When the event was created.
        correlation_id: Optional ID linking related events.
        payload: The typed event payload.
        metadata: Additional unstructured metadata.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str = Field(..., description="Event type identifier")
    context: str | dict[str, Any] = Field(
        default="https://celine-project.eu/contexts/dt-event.jsonld",
    )
    source: EventSource
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: str | None = Field(
        default=None, description="Correlation ID for tracing"
    )
    payload: T
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def type(self) -> str:
        """Alias for event_type for convenient access."""
        return self.event_type

    @model_serializer
    def serialize_model(self) -> dict[str, Any]:
        """Custom serializer to output @type and @context for JSON-LD."""
        payload_data = (
            self.payload.model_dump()
            if hasattr(self.payload, "model_dump")
            else self.payload
        )

        result: dict[str, Any] = {
            "@type": self.event_type,
            "@context": self.context,
            "id": self.id,
            "source": self.source.model_dump(),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "payload": payload_data,
            "metadata": self.metadata,
        }

        if self.correlation_id:
            result["correlation_id"] = self.correlation_id

        return result


# =============================================================================
# Generic App Execution Events (these ARE core, not module-specific)
# =============================================================================


class AppExecutionStartedPayload(BaseModel):
    """Payload for app execution started events."""

    app_key: str
    request_id: str
    config_hash: str | None = None


class AppExecutionCompletedPayload(BaseModel):
    """Payload for app execution completed events."""

    app_key: str
    request_id: str
    duration_ms: int
    result_type: str
    result_summary: dict[str, Any] = Field(default_factory=dict)


class AppExecutionFailedPayload(BaseModel):
    """Payload for app execution failed events."""

    app_key: str
    request_id: str
    error_type: str
    error_message: str
    severity: EventSeverity = EventSeverity.ERROR


class StateChangePayload(BaseModel):
    """Payload for state change events."""

    app_key: str
    previous_status: str | None
    new_status: str
    changed_fields: list[str] = Field(default_factory=list)


class AlertPayload(BaseModel):
    """Payload for alert events."""

    alert_id: str
    title: str
    description: str
    severity: EventSeverity
    app_key: str | None = None
    threshold_value: float | None = None
    actual_value: float | None = None
    suggested_action: str | None = None


# =============================================================================
# Event Type Constants
# =============================================================================


class EventTypes:
    """Constants for core event types."""

    APP_EXECUTION_STARTED = "dt.app.execution-started"
    APP_EXECUTION_COMPLETED = "dt.app.execution-completed"
    APP_EXECUTION_FAILED = "dt.app.execution-failed"
    APP_STATE_CHANGED = "dt.app.state-changed"
    ALERT_RAISED = "dt.alert.raised"


# =============================================================================
# Factory Functions for Core Events
# =============================================================================


def create_app_started_event(
    app_key: str,
    request_id: str,
    app_version: str = "unknown",
    config_hash: str | None = None,
    correlation_id: str | None = None,
) -> DTEvent[AppExecutionStartedPayload]:
    """Create an app execution started event."""
    return DTEvent[AppExecutionStartedPayload](
        event_type=EventTypes.APP_EXECUTION_STARTED,
        source=EventSource(app_key=app_key, app_version=app_version),
        correlation_id=correlation_id,
        payload=AppExecutionStartedPayload(
            app_key=app_key,
            request_id=request_id,
            config_hash=config_hash,
        ),
    )


def create_app_completed_event(
    app_key: str,
    request_id: str,
    duration_ms: int,
    result_type: str,
    app_version: str = "unknown",
    result_summary: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> DTEvent[AppExecutionCompletedPayload]:
    """Create an app execution completed event."""
    return DTEvent[AppExecutionCompletedPayload](
        event_type=EventTypes.APP_EXECUTION_COMPLETED,
        source=EventSource(app_key=app_key, app_version=app_version),
        correlation_id=correlation_id,
        payload=AppExecutionCompletedPayload(
            app_key=app_key,
            request_id=request_id,
            duration_ms=duration_ms,
            result_type=result_type,
            result_summary=result_summary or {},
        ),
    )


def create_app_failed_event(
    app_key: str,
    request_id: str,
    error_type: str,
    error_message: str,
    app_version: str = "unknown",
    severity: EventSeverity = EventSeverity.ERROR,
    correlation_id: str | None = None,
) -> DTEvent[AppExecutionFailedPayload]:
    """Create an app execution failed event."""
    return DTEvent[AppExecutionFailedPayload](
        event_type=EventTypes.APP_EXECUTION_FAILED,
        source=EventSource(app_key=app_key, app_version=app_version),
        correlation_id=correlation_id,
        payload=AppExecutionFailedPayload(
            app_key=app_key,
            request_id=request_id,
            error_type=error_type,
            error_message=error_message,
            severity=severity,
        ),
    )


def create_alert_event(
    alert_id: str,
    title: str,
    description: str,
    severity: EventSeverity,
    app_key: str | None = None,
    app_version: str = "unknown",
    threshold_value: float | None = None,
    actual_value: float | None = None,
    suggested_action: str | None = None,
    correlation_id: str | None = None,
) -> DTEvent[AlertPayload]:
    """Create an alert event."""
    return DTEvent[AlertPayload](
        event_type=EventTypes.ALERT_RAISED,
        source=EventSource(app_key=app_key or "system", app_version=app_version),
        correlation_id=correlation_id,
        payload=AlertPayload(
            alert_id=alert_id,
            title=title,
            description=description,
            severity=severity,
            app_key=app_key,
            threshold_value=threshold_value,
            actual_value=actual_value,
            suggested_action=suggested_action,
        ),
    )
