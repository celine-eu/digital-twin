from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/apps/battery-sizing", tags=["app-battery-sizing"])

@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
