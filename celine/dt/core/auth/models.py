# celine/dt/core/auth/models.py
from dataclasses import dataclass
import time


@dataclass
class AccessToken:
    access_token: str
    expires_at: float
    refresh_token: str | None = None

    def is_valid(self, leeway: int = 30) -> bool:
        """
        Returns True if token is still valid.
        `leeway` avoids edge-of-expiry races.
        """
        return time.time() < (self.expires_at - leeway)
