# celine/dt/domains/energy_community/routes/balance.py
"""Energy balance routes."""
from fastapi import APIRouter, Depends, Query

from celine.dt.api.context import get_ctx, get_ctx_auth, Ctx
from celine.dt.domains.participant.dependencies import (
    ParticipantCtx,
    get_participant_ctx,
)


__prefix__ = ""  # mounted at /{entity_id}/
__tags__ = []

router = APIRouter()


@router.get("/energy-balance", operation_id="energy_balance")
async def get_energy_balance(
    ctx: ParticipantCtx = Depends(get_participant_ctx),
    start: str | None = Query(None),
    end: str | None = Query(None),
):
    """Get energy balance for community."""
    consumption = []
    generation = []

    if start and end:
        try:
            r = await ctx.fetch_value(
                "consumption_timeseries", {"start": start, "end": end}
            )
            consumption = r.items
        except:
            pass
        try:
            r = await ctx.fetch_value(
                "generation_timeseries", {"start": start, "end": end}
            )
            generation = r.items
        except:
            pass

    total_c = sum(x.get("kwh", 0) for x in consumption)
    total_g = sum(x.get("kwh", 0) for x in generation)

    return {
        "community_id": ctx.entity.id,
        "domain": ctx.domain.name,
        "gse_zone": ctx.entity.metadata.get("gse_zone"),
        "period": {"start": start, "end": end},
        "total_consumption_kwh": total_c,
        "total_generation_kwh": total_g,
        "user": ctx.user.sub if ctx.user else None,
    }


@router.get("/energy-balance/hourly", operation_id="energy_balance_hourly")
async def get_hourly(
    ctx: ParticipantCtx = Depends(get_participant_ctx),
    date: str = Query(...),
):
    """Hourly breakdown."""
    start = f"{date}T00:00:00Z"
    end = f"{date}T23:59:59Z"

    try:
        r = await ctx.fetch_value(
            "consumption_timeseries", {"start": start, "end": end}
        )
        data = r.items
    except:
        data = []

    return {
        "community_id": ctx.entity.id,
        "date": date,
        "data": data,
    }
