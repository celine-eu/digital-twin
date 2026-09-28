# celine/dt/core/clients/errors.py
"""
Errors a data client raises that the values routes answer with a coded status.
"""
from __future__ import annotations


class ServiceIdentityUnavailable(RuntimeError):
    """The Digital Twin's own identity was asked for, and none is available (REQ-1129).

    A client raises it instead of sending a request when it has no request context to
    forward and either no token provider to authenticate with, or a provider that fails
    to obtain a token (identity provider down or refusing the client credentials). The
    values routes answer it 503 with ``code``.
    """

    code = "service_identity_unavailable"

    def __init__(self, message: str = "The Digital Twin has no service identity configured") -> None:
        self.message = message
        super().__init__(message)

    def to_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message}
