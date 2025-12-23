from abc import ABC, abstractmethod
import stat

from celine.dt.contracts.state import AppState, AppStatus
from celine.dt.core.utils import utc_now


class StateStore(ABC):

    @abstractmethod
    async def get(self, app: str) -> AppState | None: ...

    @abstractmethod
    async def set(self, state: AppState) -> None: ...

    @abstractmethod
    async def update(self, app: str, **patch) -> AppState: ...


class MemoryStateStore(StateStore):
    def __init__(self):
        self._state: dict[str, AppState] = {}

    async def get(self, app: str) -> AppState | None:
        return self._state.get(app)

    async def set(self, state: AppState) -> None:
        self._state[state.app] = state

    async def update(self, app: str, **patch) -> AppState:
        state = self._state.get(app)

        if state is None:
            state = AppState(
                app=app,
                status=AppStatus.IDLE,
                last_run_id=None,
                updated_at=utc_now(),
            )

        # Apply patch safely
        for key, value in patch.items():
            if not hasattr(state, key):
                raise ValueError(f"Invalid state field '{key}' for AppState")
            setattr(state, key, value)

        state.updated_at = utc_now()
        self._state[app] = state
        return state


def get_state_store(store_type: str = "memory"):
    if store_type == "memory":
        return MemoryStateStore()
    raise Exception(f"state store {store_type} not supported")
