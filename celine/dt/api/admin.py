from __future__ import annotations

import logging
from fastapi import APIRouter, Depends
from sqlmodel import Session

from celine.dt.core.db import get_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/retention/run")
def run_retention(session: Session = Depends(get_session)) -> dict:
    # PoC placeholder: implement pruning policies here
    # Example: delete old dt_timeseries beyond N months, etc.
    logger.info("Retention job executed (noop)")
    return {"status": "ok", "message": "noop"}
