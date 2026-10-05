# ADR-0004 — A participant twin is addressed by the caller's `sub`, and its meters are the caller's registry assets

**Date:** 2026-10-05
**Status:** accepted

## Context

`/participants/{participant_id}` names a person. Until this decision the domain resolved the
entity from the caller's registry membership and ignored the identifier in the path, and the
fetchers took whatever `device_id` the payload carried. What a caller actually received was
still their own: the registry routes answer "what is mine" for the presented token, and every
device-keyed table the fetchers read carries dataset-api's `rec_registry` row filter, which
narrows rows to the caller's meters. The Digital Twin itself, though, enforced neither the
participant nor the meter, so its own answer depended entirely on the layers behind it.

Three ways to tie a caller to a participant were open:

- **The token's `sub`.** Every consumer (`celine-webapp`, `celine-ai-assistant`,
  `flexibility-api`) already sends `participant_id = user.sub` with the user's own token. The
  claim is verified here, before any other service is asked.
- **The registry member key.** Stable and business-meaningful, but known only after a
  registry round trip, shared by everyone acting for one member, and absent from every
  consumer call today.
- **Groups.** A token's organization groups name a community and a role in it, never a
  person; they cannot say which participant a caller is.

The meters had one candidate source, the registry's `/user/assets` for the caller's token: it
is the answer dataset-api's row filter is built from, so the two layers cannot disagree on
what "own" means.

## Decision

The participant is the caller: `participant_id` MUST equal the `sub` of the token
`require_user` verified, checked before the registry is asked. A `device_id` in a fetch
payload MUST be the `sensor_id` of one of the caller's registry assets, read with the caller's
token. Refusals answer 403 and are recorded by the access audit (`participant_not_caller`,
`device_not_owned`). No role, group or service account is exempt: the Digital Twin grants no
role-based access to participant routes, and adds none. The requirements are
`docs/specifications/participant.md`.

The meter check is a domain hook, `DTDomain.check_fetch` (REQ-1116), called by the values
executor with the validated payload, so every route reaching a fetcher — both verbs of
`/values`, `/ontology` — is covered by one check rather than one per route.

## Consequences

- A fetch naming a meter costs one more registry call per request (cached on the request).
- A manager or platform view of someone else's meters cannot be built on participant routes.
  It belongs on a route of its own with its own rule, or on dataset-api directly, where the
  platform-wide grant is defined and audited.
- If the platform ever lets one person act for several participants (a household, a proxy),
  `sub` equality is the line to revisit; the tempting shortcut — accepting the member key in
  the path — would let everyone acting for one member read each other's twin.
