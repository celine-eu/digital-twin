# Specification — participant domain

Requirements specific to the `it-participant` domain (`src/celine/dt/domains/participant/`):
whose twin a caller may read, and which meters a fetch may name. The generic refusal hook is
REQ-1116 in [values.md](values.md); the audit record a refusal produces is REQ-1081 in
[runtime.md](runtime.md). Why the participant is the token's `sub`, and not a member key or
a group, is [ADR-0004](../decisions/ADR-0004-a-participant-twin-is-addressed-by-the-callers-sub.md).

---

## The participant is the caller

### REQ-1400 — A request whose `participant_id` is not the verified token's `sub` MUST answer 403, MUST be recorded `denied` with the reason `participant_not_caller`, and MUST NOT reach the REC registry or the data client.

Holds for every route under `/participants/{participant_id}`: the built-in ones and the
domain's own (`/profile`, `/assets`, `/energy-balance`, ...). The answer is the same whether
or not the named participant exists.

### REQ-1401 — A request whose `participant_id` is the caller's `sub` MUST resolve as before: the registry is asked with the caller's token, and a caller with no membership answers 404 (REQ-1031).

## The meters are the caller's

### REQ-1402 — A fetch whose payload carries a `device_id` that is not the `sensor_id` of one of the caller's registry assets MUST answer 403, MUST be recorded `denied` with the reason `device_not_owned`, and MUST NOT reach the data client.

The caller's assets are read from the registry's `/user/assets` with the caller's own token,
the same answer dataset-api's `rec_registry` row filter narrows by. A member owning no
metered asset owns no `device_id`. A fetch whose payload names no `device_id` is not checked
and does not ask the registry. Holds on `/values/{fetcher_id}` (both verbs) and on
`/ontology/{spec_id}` (REQ-1116).

## No role widens the scope

### REQ-1403 — REQ-1400 and REQ-1402 MUST hold for every caller: a realm role (`platform-admin`), an organization group and a service account MUST NOT widen them.

> The Digital Twin grants no role-based access to participant routes; it has none to keep.
> Platform-wide reads remain dataset-api's to grant and to audit, on dataset-api's own
> routes. A service account is no registry member, so it never had a participant twin to
> read (REQ-1401's 404).

## Failing closed

### REQ-1404 — When the caller's assets cannot be read from the registry, a fetch naming a `device_id` MUST answer an error and MUST NOT reach the data client.

A registry failure is never read as "owns nothing" (which would hide a member's own data
behind a 403) nor as "owns everything".

## The community's own figures

### REQ-1405 — A participant fetcher that reads a community-wide table MUST restrict it to the caller's own community, `community_id = <the resolved entity's community_key>`, rendered through `sql_quote`; a caller whose membership names no community MUST get no rows.

`total_meters_forecast` is one series per community (celine-pipelines
`every-rec-row-carries-its-community`). Without the predicate, `DISTINCT ON (timestamp)` picks one
community's row per timestamp at random once there are two. `sql_quote` renders a missing key
as `NULL`, and `community_id = NULL` matches nothing: fail closed, never another community's
series.

`meter_anomalies` reads a device-grain table (`meters_data_15m_missing_intervals`) and needs no
community predicate. Over HTTP it forwards the caller's token (REQ-1121), and dataset-api's
`rec_registry` filter narrows it to the caller's meters. The meter-anomalies handler reads it as
the Digital Twin (REQ-1133) across every community on purpose: each nudge goes to the meter's
owner with the community the registry gives the asset.
