# Community fetcher row limits are sized against a wrong rows-per-day figure

Re-verified against the code on 2026-08-14. Everything below still holds.

## The trap

`rec_self_consumption` (`src/celine/dt/domains/energy_community/domain.py:38`) selects from
`ds_dev_gold.rec_virtual_consumption_15m` with **no `rec_id` predicate, no `GROUP BY ts` and
no `SUM`**. That table is keyed `(ts, rec_id, substation_id)` and the community spans three
substations, so the fetcher returns two to three rows per timestamp.

**The displayed totals are correct anyway.** The webapp BFF sums every returned row and
accumulates its daily trend with `+=`, so the substation dimension collapses at the consumer.

That is the trap: **do not verify a fix by watching the numbers.** They will not move. Anyone
testing that way concludes the fetcher was fine and closes the work.

## What is actually broken

The row limit. The comment at `domain.py:52` justifies `limit=9000` as

> 30-day window at 15-min granularity = 30 × 288 = 8,640 rows

15-minute granularity is **96 rows per day**, not 288. The 3× is the substation count,
misread as granularity. Observed: 192 rows/day at two substations, 288 at three. The newest
9,000 rows therefore span about 31 days against a 30-day threshold — roughly a day and a half
of headroom. A fourth substation cuts coverage to about 23 days.

**This already fired once.** The same comment records that 5,000 "truncated the tail at ~17
days" — which is `5000 / 288`, the same multiplication, patched at the time by raising the
ceiling. That escape route is now closed: the dataset API caps at `MAX_LIMIT = 10_000`.

**Truncation removes the newest data, silently.** The query is `ORDER BY ts ASC` and the
dataset API applies `LIMIT`/`OFFSET` after ordering, so an over-limit window drops recent days
with no error. The trend simply stops before today.

## The neighbours

- `rec_self_consumption_daily` aggregates with `SUM(...) GROUP BY CAST(ts AS date)` at
  `limit=370`, so substations collapse correctly and it is not near truncation. It also lacks
  the `rec_id` filter.
- The `288/day` comment is copy-pasted onto `rec_virtual_consumption_per_device_15m` in the
  participant domain, where it is simply wrong — that query filters by `device_id`, so 96
  rows/day and `limit=9000` covers about 93 days. Harmless, but it spreads the bad mental
  model, which is how the original error survived review.

## Ontology consequence

The mapper spec `obs_rec_energy.yaml` mints an IRI per `(community_key, ts)`, so it **collides
across the two-to-three substation rows sharing a `ts`** and observations overwrite each other.
This resolves by construction once the fetcher aggregates — it is a symptom, not a separate
fix.

Two modelling problems in the same spec are independent of the row count: `observedProperty` is
`property/self-consumption-kw`, a kW unit on a kWh quantity and a singular name for a
collective one; and `self_consumption_ratio` is bound to `rdf:value` although a per-substation
ratio is not summable.

## Status

The defect itself belongs in the issue tracker, not here — this repository's contract keeps
defects out of `.agents/`. At the time of writing it is **unfiled**, and it is deliberately
given no identifier. What is recorded here is the part that survives the fix: why the numbers
cannot be used to verify it, and where the rows-per-day figure came from.
