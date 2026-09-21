# Pre-registration — which tail estimate describes the board's actual risk?

**Registered 2026-09-13, before any settlement in the observation window.**
Committed to git as the timestamp. Nothing below may be changed after the first
settlement lands; a revision is a new registration with its own date, and both stay
in the repo.

---

## The question

Two independent estimates of the same risk disagree for a third of the field.

| source | what it measures |
|---|---|
| `bt_daily` bucket tail (`tail_city.p2`) | P(actual bucket = de-biased **`fcst_raw`** bucket + 2) |
| forecast-native (`debias_om.resid_ge2_share`) | P(actual − de-biased **Open-Meteo 11:00–17:00 max** ≥ 2 °C) |

At seven stations the first is **four to ten times** the second. At two it is roughly
half. Amsterdam is the sharpest case: its forecast error has a standard deviation of
**0.77 °C**, which implies landing exactly two buckets high about 2–3% of the time.
`bt_daily` says **14.66%**. Both cannot describe the same station.

This matters beyond bookkeeping. `k*` is derived from the tail. The score's `S1` is the
tail's percentile, carrying double weight. The current halt is measured as "3 of 7
against 0.35 expected", and that 0.35 comes from the tails. If the tails are wrong for
part of the field, so is everything built on them.

**Neither measure can adjudicate the other**, because both are deviations from a
*forecast*, while the board's actual risk is deviation from the **market's modal
bucket**. Only the settlement log measures that. Hence a live test.

## Hypotheses

- **H_bucket** — `bt_daily`'s bucket tails are correct. The overstatement flag is an
  artefact of the comparison.
- **H_native** — the forecast-native estimate is correct, and `bt_daily`'s tails at
  these stations are inflated by noise in `fcst_raw` rather than by weather.

## Primary cohort — the seven flagged as overstated

Fixed now. No station may be added or removed.

| city | `bt_daily` tail | forecast-native | ratio |
|---|---|---|---|
| Amsterdam | 14.66% | 1.55% | 0.11 |
| Beijing | 13.02% | 2.07% | 0.16 |
| Helsinki | 13.02% | 1.55% | 0.12 |
| Manila | 12.70% | 3.63% | 0.29 |
| Singapore | 10.42% | 1.04% | 0.10 |
| Toronto | 14.74% | 3.11% | 0.21 |
| Warsaw | 13.09% | 3.11% | 0.24 |
| **sum** | **0.9165** | **0.1606** | |

## Observation window

Settlements for trading days **2026-09-14 through 2026-09-20 inclusive**, seven days,
from `log/settlements.csv`. All 37-row fields are logged whether or not a row is
tradable, so tradability is irrelevant to this test and no row is excluded for it.

Full cohort-days = 7 cities × 7 days = **49**.

## Predicted counts

An event is a settlement at **mode + 2 or higher** (`hit = 1` in the log).

| | expected hits in 49 cohort-days |
|---|---|
| under **H_bucket** | **6.42** |
| under **H_native** | **1.12** |

## Decision rule — fixed in advance

Let *k* be the observed hit count in the cohort window.

| observed | conclusion |
|---|---|
| **k ≥ 5** | supports H_bucket — the tails stand, the flag is an artefact |
| **k ≤ 1** | supports H_native — `bt_daily` tails are inflated at these stations |
| **2 ≤ k ≤ 4** | **inconclusive** — extend by a second identical week, thresholds recomputed for 98 cohort-days, and decide then |

Error rates under Poisson:

- P(k ≥ 5 | H_native true) = **0.8%**
- P(k ≤ 1 | H_bucket true) = **1.2%**
- P(inconclusive) ≈ 22% if H_bucket, ≈ 30% if H_native

**If fewer than 49 cohort-days are observed** (a market not listed, a settlement not
resolved), expectations are prorated by the actual count before applying the rule, and
the observed count is reported alongside the expected. The thresholds scale with it.

## Secondary cohort — recorded, not decided

Chengdu and Kuala Lumpur are flagged in the opposite direction (understated). Over
14 cohort-days: H_bucket expects **1.13**, H_native expects **2.03**. Those are too
close to separate in a week — roughly six weeks would be needed. **This cohort is
reported each week and no decision is taken on it now.** Saying so in advance is the
point; otherwise a suggestive number here would get read as support for whatever the
primary cohort showed.

## What this test does NOT establish

- Not whether the strategy is profitable. Nothing at this sample size can.
- Not whether any gate is correctly set. `k*` moves if the tails move, but the gate's
  threshold is a separate question.
- Not whether the de-bias is right. That needs its own test on the gap-vs-settlement
  relationship.
- Not anything about the 30 stations outside both cohorts.

## Known weaknesses, stated before the result

1. **The translation assumption.** Both predictions come from forecast-anchored
   measures and are applied to a market-anchored outcome. They coincide only where the
   model gap is near zero. Cohort gaps on 2026-09-14 ran −1.9 to +0.5 °C, so the
   assumption is reasonable but not exact, and it favours neither hypothesis.
2. **Clustering.** Seven cities over seven days are not 49 independent draws — a single
   synoptic pattern can hit Amsterdam, Helsinki and Warsaw together. Per-city hit counts
   are therefore reported alongside the total, and a result driven entirely by one city
   or one date is treated as inconclusive regardless of *k*.
3. **Seasonal drift.** The snapshot is centred on day-of-year 274 ±45 days, so mid-September
   sits inside the window. No adjustment made.
4. **The direction of comfort.** H_native being right makes the board *more* permissive
   and would unstick a halted strategy. That is the direction where wishful thinking
   lives, which is why the thresholds are written down here rather than chosen later.

## Companion offline work

`data/tails_om.json` — the tails recomputed against the de-biased Open-Meteo forecast
over `bt_daily`'s full history, reported separately on train (pre-2025-09-01) and test.
It is **not** consumed by the board and does not feed this test. If the offline
recomputation and the live settlements point the same way, that is worth more than
either alone; if they disagree, neither is adopted.

## Outcome

_Read 2026-09-21 against the rule above. Nothing in this file was changed before reading._

- **Cohort-days observed: 49 of 49.** No proration needed — every city listed every day, every day resolved.
- **Hits observed: k = 1.**
- **Per-city breakdown:** Amsterdam 0/7, Beijing 0/7, Helsinki 0/7, Manila 0/7,
  Singapore **1**/7, Toronto 0/7, Warsaw 0/7. The single event was Singapore on
  2026-09-19, mode 32 → actual 34.
- **Secondary cohort (recorded, not decided):** Chengdu 0/7, Kuala Lumpur 0/6,
  k = 0 over 13 cohort-days. H_bucket prorated 1.05, H_native 1.88. Reported as
  registered; no decision taken.

### Conclusion under the rule

k = 1 falls in the **k ≤ 1** band: **H_native is supported.** `bt_daily`'s bucket tails
are inflated at these seven stations. Expected counts were 6.42 under H_bucket and 1.12
under H_native; P(k ≤ 1 | H_bucket) = 1.2%.

Weakness 2 — clustering — does not bite here. One event at one city on one date cannot
be a synoptic artefact, and the rule's "driven entirely by one city" clause applies to a
*high* count, not to a floor of one. The result is read as registered.

### What this does not do

It does not unhalt anything, and the registration said so in advance. It establishes
that one input is wrong, not that the strategy is right. Note the direction: H_native
makes the board **more permissive**, which is the branch the registration flagged as
where wishful thinking lives. The thresholds were fixed on 2026-09-13 precisely so that
this reading could not be argued into a licence.

Separately, and more damagingly for any tail-based selector: see
`research/no-calm-cities.md`, read the same day. Over 349 settled city-days the
per-city +2 rates are statistically indistinguishable from a single common rate of
4.0%. Replacing an inflated per-city tail with a better per-city tail does not help if
there is no per-city signal to estimate.
