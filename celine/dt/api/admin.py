from __future__ import annotations

import logging
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

async def run_retention(*, session: AsyncSession) -> dict:
    # PoC placeholder: implement pruning policies here
    logger.info("Retention job executed (noop)")
    return {"status": "ok", "message": "noop"}
