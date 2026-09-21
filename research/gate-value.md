# Result — every gate measured, and what the price already knows

**Run 2026-09-21.** Joins `predictions/*.json` (the **whole field**, all gate values, eight
trading days) to `log/settlements.csv`. 285 joined city-days, 252 with a tradable bid,
**11 hits** (10 among tradable rows).

This is the gate-value measurement proposed on 2026-09-14: score each gate against real
outcomes, then weight them. It turns out the measurement answers a different and larger
question than the one it was built for.

---

## 1. First, a correction about what the gates are

The board is described as selecting on weather. It mostly does not. Of the inputs:

| kind | inputs |
|---|---|
| **weather** | `rain_mm`, `cloud_pct` |
| **statistical** | `tail`, `n`, `kstar`, `sd`, `pop_conservative` |
| **price-derived** | `bid`, `break_even`, `mult`, `ev`, `S2`, `mode_share`, `depth` |
| **model vs market** | `gap` |

Two of fourteen are weather. `mode_share` looks like a market-structure gate but is
computed from ladder mids, so it is a price. `mult` is `break_even ÷ tail` — price
divided by a statistic. Any weighting exercise is therefore mostly a weighting of the
price against itself.

## 2. Discrimination of every input

AUC against `hit = 1` (`actual − market mode ≥ 2`), 600-sample bootstrap CI.
AUC 0.5 is no discrimination; `*` marks a CI excluding 0.5.

| input | n | AUC | 95% CI | low tercile | high tercile |
|---|---|---|---|---|---|
| `S2` (percentile of mult) | 285 | 0.793 | [0.619, 0.933] | 1.1% | 8.4% * |
| `bid` | 285 | 0.782 | [0.598, 0.925] | 1.1% | 9.5% * |
| `mult` | 285 | 0.776 | [0.603, 0.928] | 1.1% | 8.4% * |
| `ev` | 285 | 0.767 | [0.590, 0.937] | 2.1% | 8.4% * |
| `break_even` | 252 | 0.759 | [0.570, 0.932] | 1.2% | 8.3% * |
| `mode_share` | 285 | 0.274 | [0.161, 0.429] | 7.4% | 1.1% * |
| `gap` | 285 | 0.287 | [0.143, 0.452] | 6.3% | 1.1% * |
| `score` (the composite) | 285 | 0.646 | [0.476, 0.810] | 2.1% | 6.3% |
| `pen` | 285 | 0.621 | [0.442, 0.795] | 2.1% | 7.4% |
| `S1` (percentile of POP) | 285 | 0.588 | [0.422, 0.753] | 3.2% | 6.3% |
| `depth` | 285 | 0.584 | [0.347, 0.809] | 3.2% | 5.3% |
| `rain_mm` | 285 | 0.579 | [0.412, 0.763] | 2.1% | 6.3% |
| `pop_conservative` | 252 | 0.547 | [0.360, 0.760] | 3.6% | 4.8% |
| `cloud_pct` | 285 | 0.473 | [0.335, 0.611] | 3.2% | 3.2% |
| `kstar` | 285 | 0.462 | [0.312, 0.618] | 5.3% | 5.3% |
| `sd` | 252 | 0.439 | [0.223, 0.661] | 4.8% | 3.6% |
| `tail` (`bt_daily`) | 285 | 0.420 | [0.245, 0.579] | 5.3% | 3.2% |
| `n` | 285 | 0.389 | [0.212, 0.588] | 6.3% | 4.2% |

Read it in three parts.

**The five starred rows at the top are one variable.** `S2` is the percentile of `mult`,
`mult` is `break_even ÷ tail`, `break_even` is a monotone function of `bid`, and `ev` is
a function of `bid` and an assumed risk. They are the price, counted five times. The
price predicts the outcome at AUC ≈ 0.78, in the direction that expensive buckets hit
more often.

**`mode_share` and `gap` are also mostly price.** `mode_share` comes from ladder mids;
a diffuse ladder is the market saying the day is uncertain, and those days hit more. The
`gap` result (low gap → more hits) sits against the 2026-09-19 regression, which found
slope −0.043 on continuous `dev`, and with 11 events and 18 features tested it is what a
single false positive looks like. Not treated as a finding.

**Everything that is not price shows nothing.** `tail` is at 0.420 — mildly *anti*-
predictive, consistent with the inverted terciles in `STATUS.md`. And the two actual
weather inputs, `rain_mm` at 0.579 and `cloud_pct` at 0.473, both straddle 0.5.

**The composite `score` straddles 0.5** — CI [0.476, 0.810]. The entire scoring
apparatus, all gates and penalties combined, has not demonstrated discrimination.

## 3. The market is calibrated

If price predicts hits, the question is whether it predicts them *correctly*. Grouping
the 252 tradable rows by quoted bid, and comparing each band's realized rate to the
break-even its own price implies (`fee = 0.05 × min(bid, 1−bid)`):

| band | n | hits | realized | break-even | mean bid | P/L per $ risked |
|---|---|---|---|---|---|---|
| 0.001–0.02 | 119 | 0 | 0.0% | 1.0% | 0.011 | +1.05% |
| 0.02–0.04 | 50 | 2 | 4.0% | 3.4% | 0.036 | −0.62% |
| 0.04–0.07 | 40 | 3 | 7.5% | 5.2% | 0.054 | −2.46% |
| 0.07–0.12 | 32 | 3 | 9.4% | 9.2% | 0.096 | −0.24% |
| > 0.12 | 11 | 2 | 18.2% | 15.5% | 0.164 | −3.12% |
| **all tradable** | **252** | **10** | **4.0%** | **3.8%** | **0.040** | **−0.15%** |
| old selector | 30 | 4 | 13.3% | 6.5% | 0.069 | **−7.29%** |

Realized tracks break-even across the whole range: 0.0 against 1.0, 4.0 against 3.4, 7.5
against 5.2, 9.4 against 9.2, 18.2 against 15.5. Selling the whole field returns
**−0.15% per dollar risked**, day-clustered bootstrap 95% CI **[−1.68%, +1.52%]**.

That is a fairly priced market. The zero hits in the cheapest band are the only thing
resembling an edge and at a 1.0% break-even the expectation was 1.2 events, so zero is
unremarkable.

**AUC 0.78 on price is not an exploitable signal. It is the market being right.**

## 4. Why gate weighting cannot fix this

The proposal was: measure each gate's value, weight accordingly, select the ten best
rows. Three problems, in increasing order of seriousness.

**Power.** At 36 cities/day and a 4.0% rate, the field yields ≈ 1.4 events/day. Fitting
weights needs roughly 10 events per free parameter, and an independent sample of the
same size to validate — otherwise the weights are a description of eleven particular
days. Five gates is 50 events to fit and 50 to validate: **about ten weeks of
collection** before a five-parameter weighting means anything. Eleven events cannot
support one weight, let alone five.

**Multiplicity.** Eighteen inputs were tested at 95%; roughly one CI excludes 0.5 by
chance. Two of the starred results (`gap`, and arguably `mode_share`) are in exactly that
territory, and the five price variables are one test wearing five hats.

**The structural problem, which power will not cure.** A weighted score still selects
rows where the score disagrees with the price. §3 says the price is right. A selector
built on top of a calibrated price can only lose the spread and the fee — which is what
the −7.29% on the old selector is, and it is close to what 30 rows of taker fees and
adverse selection should cost.

## 5. What this leaves

- **City selection** — dead (`no-calm-cities.md`: cities are one population at 4.0%).
- **Gate weighting** — dead, and not for want of data. The inputs that could be weighted
  have no measurable signal; the one that does is the price.
- **Better tail estimates** — vindicated as estimates (`prereg-tail-adjudication.md`,
  k = 1) and worth nothing as selectors.
- **Directional +2 NO sale, at any price band** — no edge found at this sample size, and
  the band table is the reason to stop looking rather than to look harder.
- **Tail asymmetry pricing** — still open, registered, window runs to 2026-10-19. It asks
  whether the *cold* side is mispriced, which §3 does not address.
- **Market making** — untouched by any of this and the only remaining idea that does not
  require beating the price. Weather markets are `takerOnly: true` (makers pay zero),
  `rebateRate 0.25`, rewards at `rewardsMaxSpread 4.5`, `rewardsMinSize 50`. It earns
  from spread and rebates, not from forecasting, which after §3 is its strongest
  recommendation.

## 6. The honest summary

Eight days, 252 tradable rows, 10 events — provisional, and every number here should be
re-read at three times the sample. But four independent tests now point the same way:
gap trading null, mode calibrated, cities homogeneous, price bands calibrated. The
simplest description consistent with all four is that **Polymarket's daily temperature
ladders are efficiently priced at the resolution this project can measure**, and that a
directional edge was not there to be found.

That is a real result. It cost five losing rows and two weeks, and it closed a question
that could have absorbed a year.
