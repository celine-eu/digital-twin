"""Governed aggregate fetchers consumed by the REC Manager Dashboard."""

from celine.dt.contracts.values import ValueFetcherSpec


def _period_schema(*, device_id: bool = False) -> dict:
    properties: dict[str, dict[str, str]] = {
        "start": {"type": "string", "description": "Period start (ISO timestamp)"},
        "end": {"type": "string", "description": "Period end (ISO timestamp)"},
    }
    required = ["start", "end"]
    if device_id:
        properties["device_id"] = {"type": "string", "description": "Technical device ID"}
        required.append("device_id")
    return {
        "type": "object",
        "required": required,
        "additionalProperties": False,
        "properties": properties,
    }


def manager_value_specs() -> list[ValueFetcherSpec]:
    """Return device-keyed or aggregate fetchers; no participant identity is selected."""

    period = _period_schema()
    return [
        ValueFetcherSpec(
            id="rec_population_summary",
            client="dataset_api",
            query="""
                SELECT
                    NULL::integer AS administrative_members,
                    COALESCE(MAX(total_members), 0) AS monitored_members,
                    COUNT(DISTINCT device_id) AS monitored_devices,
                    NULL::integer AS unregistered_meters
                FROM ds_dev_gold.rec_gamification_summary
                WHERE ts_date >= CAST(:start AS timestamptz)::date
                  AND ts_date < CAST(:end AS timestamptz)::date
            """,
            limit=1,
            payload_schema=period,
        ),
        ValueFetcherSpec(
            id="rec_meters_health_summary",
            client="dataset_api",
            query="""
                WITH devices AS (
                    SELECT device_id, MAX(ts) AS last_seen
                    FROM ds_dev_gold.meters_data_15m
                    WHERE device_id IS NOT NULL
                    GROUP BY device_id
                )
                SELECT
                    COUNT(*) FILTER (WHERE last_seen >= CAST(:end AS timestamptz)
                                                       - INTERVAL '30 minutes') AS reporting,
                    COUNT(*) FILTER (WHERE last_seen < CAST(:end AS timestamptz)
                                       - INTERVAL '30 minutes'
                                      AND last_seen >= CAST(:end AS timestamptz)
                                                       - INTERVAL '24 hours') AS degraded,
                    COUNT(*) FILTER (WHERE last_seen < CAST(:end AS timestamptz)
                                                       - INTERVAL '24 hours') AS silent
                FROM devices
            """,
            limit=1,
            payload_schema=period,
        ),
        ValueFetcherSpec(
            id="rec_meters_missing_intervals",
            client="dataset_api",
            query="""
                WITH devices AS (
                    SELECT device_id, MIN(ts) AS first_seen, MAX(ts) AS last_seen
                    FROM ds_dev_gold.meters_data_15m
                    WHERE device_id IS NOT NULL
                    GROUP BY device_id
                ), observed AS (
                    SELECT device_id, COUNT(*) AS received_intervals
                    FROM ds_dev_gold.meters_data_15m
                    WHERE ts >= CAST(:start AS timestamptz)
                      AND ts < CAST(:end AS timestamptz)
                    GROUP BY device_id
                )
                SELECT
                    d.device_id,
                    d.first_seen,
                    d.last_seen,
                    GREATEST(0, FLOOR(EXTRACT(EPOCH FROM
                        (CAST(:end AS timestamptz) - d.last_seen)) / 60)) AS gap_minutes,
                    GREATEST(1, FLOOR(EXTRACT(EPOCH FROM
                        (CAST(:end AS timestamptz) - CAST(:start AS timestamptz))) / 900))
                        AS expected_intervals,
                    COALESCE(o.received_intervals, 0) AS received_intervals,
                    100.0 * COALESCE(o.received_intervals, 0) /
                        GREATEST(1, FLOOR(EXTRACT(EPOCH FROM
                        (CAST(:end AS timestamptz) - CAST(:start AS timestamptz))) / 900))
                        AS coverage_percent
                FROM devices d
                LEFT JOIN observed o USING (device_id)
                ORDER BY gap_minutes DESC
            """,
            limit=1000,
            payload_schema=period,
        ),
        ValueFetcherSpec(
            id="rec_device_streaks",
            client="dataset_api",
            query="""
                WITH devices AS (
                    SELECT device_id, MIN(ts) AS first_seen, MAX(ts) AS last_seen
                    FROM ds_dev_gold.meters_data_15m
                    WHERE device_id IS NOT NULL
                    GROUP BY device_id
                )
                SELECT
                    device_id,
                    CASE
                        WHEN first_seen IS NULL THEN 'never-activated'
                        WHEN last_seen >= CAST(:end AS timestamptz) - INTERVAL '7 days' THEN 'active'
                        ELSE 'dormant'
                    END AS engagement_state
                FROM devices
            """,
            limit=1000,
            payload_schema=period,
        ),
        ValueFetcherSpec(
            id="rec_points_leaderboard_community",
            client="dataset_api",
            query="""
                WITH totals AS (
                    SELECT device_id, SUM(daily_points) AS points
                    FROM ds_dev_gold.rec_participant_points
                    WHERE ts_date >= CAST(:start AS timestamptz)::date
                      AND ts_date < CAST(:end AS timestamptz)::date
                    GROUP BY device_id
                )
                SELECT
                    device_id,
                    points,
                    RANK() OVER (ORDER BY points DESC) AS rank,
                    0 AS trend
                FROM totals
                ORDER BY rank, device_id
            """,
            limit=1000,
            payload_schema=period,
        ),
        ValueFetcherSpec(
            id="rec_points_distribution",
            client="dataset_api",
            query="""
                WITH totals AS (
                    SELECT device_id, SUM(daily_points)::double precision AS points
                    FROM ds_dev_gold.rec_participant_points
                    WHERE ts_date >= CAST(:start AS timestamptz)::date
                      AND ts_date < CAST(:end AS timestamptz)::date
                    GROUP BY device_id
                ), stats AS (
                    SELECT
                        COUNT(*) AS monitored_devices,
                        COUNT(*) FILTER (WHERE points > 0) AS awarded_devices,
                        COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY points), 0)
                            AS median_points,
                        COALESCE(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY points), 0)
                            AS top_decile_points,
                        COALESCE(PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY points), 0)
                            AS bottom_decile_points
                    FROM totals
                ), buckets(label, minimum, maximum) AS (
                    VALUES ('0', 0, 0), ('1–50', 1, 50), ('51–100', 51, 100),
                           ('101–200', 101, 200), ('201–350', 201, 350), ('>350', 351, NULL)
                )
                SELECT
                    b.label,
                    b.minimum,
                    b.maximum,
                    COUNT(t.device_id) AS count,
                    s.monitored_devices,
                    s.awarded_devices,
                    s.median_points,
                    s.top_decile_points,
                    s.bottom_decile_points,
                    0 AS concentration_index
                FROM buckets b
                CROSS JOIN stats s
                LEFT JOIN totals t ON t.points >= b.minimum
                    AND (b.maximum IS NULL OR t.points <= b.maximum)
                GROUP BY b.label, b.minimum, b.maximum, s.monitored_devices,
                         s.awarded_devices, s.median_points, s.top_decile_points,
                         s.bottom_decile_points
                ORDER BY b.minimum
            """,
            limit=10,
            payload_schema=period,
        ),
        ValueFetcherSpec(
            id="rec_device_points_ledger",
            client="dataset_api",
            query="""
                SELECT
                    _id AS id,
                    ts_date::timestamptz AS occurred_at,
                    ts_date::text AS source_ref,
                    daily_settlement_points,
                    daily_bonus_points
                FROM ds_dev_gold.rec_participant_points
                WHERE device_id = :device_id
                  AND ts_date >= CAST(:start AS timestamptz)::date
                  AND ts_date < CAST(:end AS timestamptz)::date
                ORDER BY occurred_at DESC
            """,
            limit=1000,
            payload_schema=_period_schema(device_id=True),
        ),
        ValueFetcherSpec(
            id="rec_flexibility_windows_history",
            client="dataset_api",
            query="""
                SELECT
                    window_start,
                    window_end,
                    MAX(community_kwh) AS offered_kwh,
                    AVG(confidence) AS confidence,
                    MAX(flexibility_model) AS flexibility_model,
                    CASE WHEN window_end < NOW() THEN 'settled' ELSE 'upcoming' END AS state
                FROM ds_dev_gold.rec_flexibility_windows
                WHERE window_start >= CAST(:start AS timestamptz)
                  AND window_start < CAST(:end AS timestamptz)
                GROUP BY window_start, window_end
                ORDER BY window_start DESC
            """,
            limit=500,
            payload_schema=period,
        ),
        ValueFetcherSpec(
            id="rec_flexibility_chain_daily",
            client="dataset_api",
            query="""
                WITH windows AS (
                    SELECT device_id, window_start, window_end, estimated_kwh
                    FROM ds_dev_gold.rec_flexibility_windows
                    WHERE window_start >= CAST(:start AS timestamptz)
                      AND window_start < CAST(:end AS timestamptz)
                ), delivered AS (
                    SELECT device_id, window_start, window_end,
                           SUM(consumption_kwh) AS delivered_kwh
                    FROM ds_dev_gold.rec_settlement_1h
                    WHERE window_start >= CAST(:start AS timestamptz)
                      AND window_start < CAST(:end AS timestamptz)
                    GROUP BY device_id, window_start, window_end
                ), points AS (
                    SELECT device_id, ts_date,
                           SUM(daily_points) AS points
                    FROM ds_dev_gold.rec_participant_points
                    GROUP BY device_id, ts_date
                ), commitments AS (
                    SELECT device_id, ts_date, BOOL_OR(committed) AS committed
                    FROM ds_dev_gold.rec_gamification_summary
                    GROUP BY device_id, ts_date
                )
                SELECT
                    w.window_start,
                    w.window_end,
                    w.device_id,
                    COALESCE(c.committed, FALSE) AS committed,
                    CASE WHEN c.committed THEN w.estimated_kwh ELSE 0 END AS committed_kwh,
                    d.delivered_kwh,
                    w.estimated_kwh AS baseline_kwh,
                    CASE WHEN w.estimated_kwh > 0 THEN d.delivered_kwh / w.estimated_kwh END
                        AS effort_multiplier,
                    p.points
                FROM windows w
                LEFT JOIN delivered d USING (device_id, window_start, window_end)
                LEFT JOIN points p ON p.device_id = w.device_id
                                  AND p.ts_date = w.window_start::date
                LEFT JOIN commitments c ON c.device_id = w.device_id
                                       AND c.ts_date = w.window_start::date
            """,
            limit=10000,
            payload_schema=period,
        ),
    ]
