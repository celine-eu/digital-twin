from typing import Any
from pydantic import BaseModel, Field


class ValuesRequest(BaseModel):
    payload: dict[str, Any] = Field(
        default_factory=dict,
        json_schema_extra={"title": "ValuesRequestPayload"},
    )
