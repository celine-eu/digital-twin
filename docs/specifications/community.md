# Specification — community domain

Requirements specific to the `it-energy-community` domain
(`src/celine/dt/domains/energy_community/`): which community a fetch reads. The entity is the
community in the URL (`/communities/it/{community_id}`), whose id is the community's slug, the
Keycloak organisation alias and the gold `community_id` (celine-pipelines
`every-rec-row-carries-its-community`).

The domain's callers reach it with a service token as well as a user one (celine-community's
console, flexibility-api). dataset-api narrows no service account, so **which community** the
rows belong to is chosen here, by the statement. Who may read a community's **manager
fetchers** (the operator console's device-level and aggregate figures,
`manager_fetchers.py`) is decided here too; the other fetchers are open to any authenticated
caller.

---

## Every REC read names its community

### REQ-1500 — Every fetcher of the domain that reads a REC table (`ds_dev_gold.rec_*`, `ds_dev_gold.meters_*`, `ds_dev_gold.cer_energy_forecast`) MUST restrict **each** read of such a table to `community_id = <entity id>`, in the same statement, so that no row of another community contributes to its answer.

Each read means each `FROM`: a CTE that joins a second REC table carries its own predicate, so a
community's figures are never joined to another community's rows.

### REQ-1501 — The entity id MUST reach the statement only through `sql_quote`: an id carrying a quote or SQL MUST stay one literal.

The entity id comes from the URL, so it is caller-supplied. `sql_quote` doubles quotes; the
template never interpolates it raw (query-templates.md).

### REQ-1502 — A fetcher that reads no REC table (weather, PV potential, the reference boundaries) MUST NOT be restricted by community.

Those tables carry no `community_id`. A predicate there would fail every fetch.

### REQ-1503 — A manager fetcher MUST answer the device rows of the community in the URL only, whatever the caller's token: a service token through the entity route reads one community per entity.

*Verified by: e2e — on a local stack whose warehouse holds two communities, `example-rec` and
`other-rec`: the console's service token asks each manager fetcher for one community and gets
no device of the other*

---

## Who reads the manager fetchers

The manager fetchers return per-device figures of the whole community. The console reaches them
with its own service token (`svc-community`), which dataset-api's `rec_registry` filter does
not narrow, so the twin decides who may ask. The console keeps its own persona check, and names
as the entity the community it checked the persona for.

### REQ-1510 — A manager fetcher MUST be served only to a service account whose token's scopes include `digital-twin.community.manage`, to a caller holding the realm role `platform-admin`, or to a person holding the group `admins` or `managers` inside the organisation whose alias is the community in the URL. Any other caller MUST answer 403, MUST be recorded `denied` with the reason `community_not_managed` (a person) or `manager_scope_missing` (a service account), and MUST NOT reach the data client.

`digital-twin.values.read` does not admit: every service that reads the twin holds it
(flexibility-api, onboarding, celine-grid). A token that carries at least one organisation is
judged as a person, whatever its scopes, as in the grid domain (REQ-1322).

*Verified by: unit — each admitted caller reads a manager fetcher; a member (`viewers`), a manager
of another community, a person with no organisation and a service holding only
`digital-twin.values.read` are refused with the reason recorded and no call on a fake data
client*

### REQ-1511 — A group MUST count only inside the organisation the URL names: `admins` or `managers` held in another organisation MUST NOT admit a caller to this one.

### REQ-1512 — The fetchers of the domain that are not manager fetchers MUST NOT be gated by REQ-1510: any caller the route admits reads them.

flexibility-api reads the community windows and the gamification summary, and onboarding the
reference boundaries, with their own service tokens.

### REQ-1513 — Through the running services, a manager fetcher MUST refuse a member of the community and a manager of another one, and MUST serve the community's manager and the console's service token.

*Verified by: e2e — temporary realm users of `example-rec` (`viewers`, `managers`) and of
`other-rec` (`managers`), and the `svc-community` client-credentials token*
