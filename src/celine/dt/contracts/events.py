# celine/dt/contracts/events.py
"""
Event envelope for Digital Twin broker messages.

Events are self-describing, traceable, and extensible. They carry a typed
payload and enough metadata for routing, correlation, and debugging.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field, model_serializer


class EventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventSource(BaseModel):
    """Identifies the producer of an event."""

    domain: str = Field(..., description="Domain name that produced this event")
    entity_id: str | None = Field(default=None, description="Entity scoping the event")
    handler: str | None = Field(default=None, description="Handler / simulation key")
    version: str = Field(default="unknown")


T = TypeVar("T", bound=BaseModel)


class DTEvent(BaseModel, Generic[T]):
    """Standard event envelope for all Digital Twin events."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str = Field(..., description="Event type identifier")
    context: str | dict[str, Any] = Field(
        default="https://celine-project.eu/contexts/dt-event.jsonld",
    )
    source: EventSource
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    correlation_id: str | None = None
    payload: T
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_serializer
    def serialize_model(self) -> dict[str, Any]:
        payload_data = (
            self.payload.model_dump() if hasattr(self.payload, "model_dump") else self.payload
        )
        result: dict[str, Any] = {
            "@type": self.event_type,
            "@context": self.context,
            "id": self.id,
            "source": self.source.model_dump(),
            "timestamp": self.timestamp.isoformat(),
            "payload": payload_data,
            "metadata": self.metadata,
        }
        if self.correlation_id:
            result["correlation_id"] = self.correlation_id
        return result
