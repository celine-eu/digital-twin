# celine/dt/modules/ev_charging/events.py
"""
EV Charging module-specific event schemas.

These events are specific to the EV Charging module and should NOT be
in core contracts. Each module defines its own event payloads and
factory functions.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from celine.dt.contracts.events import DTEvent, EventSource


# =============================================================================
# Event Type Constants
# =============================================================================


class EVChargingEventTypes:
    """Constants for EV charging event types."""

    READINESS_COMPUTED = "dt.ev-charging.readiness-computed"
    SCHEDULE_UPDATED = "dt.ev-charging.schedule-updated"
    CAPACITY_ALERT = "dt.ev-charging.capacity-alert"


# =============================================================================
# Event Payloads
# =============================================================================


class EVChargingReadinessPayload(BaseModel):
    """
    Payload for EV Charging Readiness computed events.

    Emitted when the ev-charging-readiness app produces a new indicator.
    """

    community_id: str = Field(..., description="Energy community identifier")
    window_start: datetime = Field(..., description="Start of decision window")
    window_end: datetime = Field(..., description="End of decision window")
    window_hours: int = Field(..., description="Window duration in hours")

    # Core computed values
    expected_pv_kwh: float = Field(..., description="Expected PV generation (kWh)")
    ev_charging_capacity_kwh: float = Field(
        ..., description="Max EV charging capacity (kWh)"
    )
    pv_ev_ratio: float = Field(..., description="Ratio of PV to EV capacity")

    # Decision indicator
    indicator: Literal["OPTIMAL", "MARGINAL", "SUBOPTIMAL", "UNSTABLE"]
    confidence: float = Field(..., ge=0, le=1, description="Forecast confidence")

    # Explanations
    drivers: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    # Weather context
    mean_clouds_pct: float = Field(..., description="Mean cloud cover %")
    clouds_std_pct: float = Field(..., description="Cloud cover standard deviation")
    solar_energy_kwh_per_m2: float = Field(..., description="Total solar energy")


class EVChargingSchedulePayload(BaseModel):
    """Payload for charging schedule update events."""

    community_id: str
    schedule_id: str
    vehicle_count: int
    total_energy_kwh: float
    peak_power_kw: float
    start_time: datetime
    end_time: datetime


class EVChargingCapacityAlertPayload(BaseModel):
    """Payload for capacity alert events."""

    community_id: str
    alert_type: Literal["OVER_CAPACITY", "UNDER_UTILIZATION", "GRID_CONSTRAINT"]
    current_demand_kw: float
    available_capacity_kw: float
    threshold_pct: float
    message: str


# =============================================================================
# Factory Functions
# =============================================================================


def create_ev_charging_readiness_event(
    *,
    community_id: str,
    window_start: datetime,
    window_end: datetime,
    window_hours: int,
    expected_pv_kwh: float,
    ev_charging_capacity_kwh: float,
    pv_ev_ratio: float,
    indicator: Literal["OPTIMAL", "MARGINAL", "SUBOPTIMAL", "UNSTABLE"],
    confidence: float,
    drivers: list[str],
    recommendations: list[str],
    mean_clouds_pct: float,
    clouds_std_pct: float,
    solar_energy_kwh_per_m2: float,
    app_version: str = "1.0.0",
    instance_id: str | None = None,
    correlation_id: str | None = None,
) -> DTEvent[EVChargingReadinessPayload]:
    """
    Factory function to create an EV Charging Readiness event.

    This is the recommended way to create events from app results.
    """
    return DTEvent[EVChargingReadinessPayload](
        event_type=EVChargingEventTypes.READINESS_COMPUTED,
        source=EventSource(
            app_key="ev-charging-readiness",
            app_version=app_version,
            module="ev-charging",
            instance_id=instance_id,
        ),
        correlation_id=correlation_id,
        payload=EVChargingReadinessPayload(
            community_id=community_id,
            window_start=window_start,
            window_end=window_end,
            window_hours=window_hours,
            expected_pv_kwh=expected_pv_kwh,
            ev_charging_capacity_kwh=ev_charging_capacity_kwh,
            pv_ev_ratio=pv_ev_ratio,
            indicator=indicator,
            confidence=confidence,
            drivers=drivers,
            recommendations=recommendations,
            mean_clouds_pct=mean_clouds_pct,
            clouds_std_pct=clouds_std_pct,
            solar_energy_kwh_per_m2=solar_energy_kwh_per_m2,
        ),
    )


def create_ev_charging_schedule_event(
    *,
    community_id: str,
    schedule_id: str,
    vehicle_count: int,
    total_energy_kwh: float,
    peak_power_kw: float,
    start_time: datetime,
    end_time: datetime,
    app_version: str = "1.0.0",
    correlation_id: str | None = None,
) -> DTEvent[EVChargingSchedulePayload]:
    """Create an EV charging schedule update event."""
    return DTEvent[EVChargingSchedulePayload](
        event_type=EVChargingEventTypes.SCHEDULE_UPDATED,
        source=EventSource(
            app_key="ev-charging-scheduler",
            app_version=app_version,
            module="ev-charging",
        ),
        correlation_id=correlation_id,
        payload=EVChargingSchedulePayload(
            community_id=community_id,
            schedule_id=schedule_id,
            vehicle_count=vehicle_count,
            total_energy_kwh=total_energy_kwh,
            peak_power_kw=peak_power_kw,
            start_time=start_time,
            end_time=end_time,
        ),
    )


def create_ev_charging_capacity_alert(
    *,
    community_id: str,
    alert_type: Literal["OVER_CAPACITY", "UNDER_UTILIZATION", "GRID_CONSTRAINT"],
    current_demand_kw: float,
    available_capacity_kw: float,
    threshold_pct: float,
    message: str,
    app_version: str = "1.0.0",
    correlation_id: str | None = None,
) -> DTEvent[EVChargingCapacityAlertPayload]:
    """Create an EV charging capacity alert event."""
    return DTEvent[EVChargingCapacityAlertPayload](
        event_type=EVChargingEventTypes.CAPACITY_ALERT,
        source=EventSource(
            app_key="ev-charging-monitor",
            app_version=app_version,
            module="ev-charging",
        ),
        correlation_id=correlation_id,
        payload=EVChargingCapacityAlertPayload(
            community_id=community_id,
            alert_type=alert_type,
            current_demand_kw=current_demand_kw,
            available_capacity_kw=available_capacity_kw,
            threshold_pct=threshold_pct,
            message=message,
        ),
    )
