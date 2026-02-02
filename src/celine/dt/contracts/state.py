from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AppStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"


@dataclass
class AppState:
    app: str
    status: AppStatus
    last_run_id: str | None
    updated_at: datetime
    data: dict[str, Any] = field(default_factory=dict)
