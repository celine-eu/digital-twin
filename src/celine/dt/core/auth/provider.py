# celine/dt/core/auth/provider.py
from abc import ABC, abstractmethod
from celine.dt.core.auth.models import AccessToken


class TokenProvider(ABC):
    @abstractmethod
    async def get_token(self) -> AccessToken:
        """
        Return a valid access token.
        Implementations must refresh or re-authenticate if needed.
        """
        ...
