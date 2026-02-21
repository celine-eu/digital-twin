from dataclasses import dataclass

from starlette.datastructures import State
from celine.dt.contracts.infrastructure import Infrastructure
from celine.sdk.auth import TokenProvider

@dataclass
class AppState(State):
    infra: Infrastructure
    token_provider: TokenProvider | None = None