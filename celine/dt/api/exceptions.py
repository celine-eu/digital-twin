from __future__ import annotations

class DTError(Exception):
    pass

class NotFound(DTError):
    pass

class BadRequest(DTError):
    pass
