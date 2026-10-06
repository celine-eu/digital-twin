# Specification — community domain

Requirements specific to the `it-energy-community` domain
(`src/celine/dt/domains/energy_community/`): which community a fetch reads. The entity is the
community in the URL (`/communities/it/{community_id}`), whose id is the community's slug, the
Keycloak organisation alias and the gold `community_id` (celine-pipelines
`every-rec-row-carries-its-community`).

The domain's callers reach it with a service token as well as a user one (celine-community's
console, flexibility-api). dataset-api narrows no service account, so **which community** the
rows belong to is chosen here, by the statement. Whether the caller may read that community is
not decided here.

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
