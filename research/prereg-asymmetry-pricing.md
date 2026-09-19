# Pre-registration — is the left skew priced?

**Registered 2026-09-19, before any ladder has been captured.**
Committed to git as the timestamp. Nothing below may be changed once the first row
lands in `log/ladders.csv`; a revision is a new registration with its own date, and
both stay in the repo.

---

## The question

The risk side is measured. Over 242 settled city-days, `dev = actual − market mode`:

| | |
|---|---|
| P(dev ≥ +2) — hot | **3.72%** [2.0–6.9] |
| P(dev ≤ −2) — cold | **7.02%** [4.4–11.0] |
| ratio cold ÷ hot | **1.89×** |

The ±1 buckets are symmetric (64 hot, 63 cold); the asymmetry is entirely in the
tails and deepens at ±3 (1 hot, 7 cold). There is a physical reason to expect it: a
daily maximum has a hard ceiling in clear-sky insolation but no floor short of cold
advection.

**What is not measured is the price.** If the book quotes `mode−2` and `mode+2` alike
while their true risks differ by 1.9×, selling the cold side is a systematically bad
trade and selling the hot side is the better one — which is the opposite of what a
naive "sell whichever tail pays more" rule would do. If the book already charges more
for the cold side, there is nothing here.

This is not a strategy. The +2 board is halted and stays halted. This registration
exists so that a number arriving in three weeks is read against a threshold written
before the data, rather than the other way round — which is the discipline that
closed gap trading and mode mispricing in one afternoon.

## Data

`selfcheck/capture_ladders.py`, added 2026-09-19, runs inside the existing board
workflow at ~04:30 UTC and records the **whole ladder for the whole field**, including
rows no gate would pass. Conditioning the price sample on the selector is precisely
the error that produced the adverse selection the strategy died of; this avoids
repeating it in the diagnostic.

- `ladders/YYYY-MM-DD.json` — raw: every bucket's title, bid, ask, liquidity, volume.
- `log/ladders.csv` — derived, one row per city-day, all of it recomputable from the raw.

The two quantities under test, both normalized by the book sum:

- `cum_up2` = Σ implied probability of buckets ≥ mode+2
- `cum_dn2` = Σ implied probability of buckets ≤ mode−2

Cumulative, not the single bucket, because the risk being priced is "at least this far",
which is what `dev ≥ 2` and `dev ≤ −2` measure.

## Observation window

Captures for trading days **2026-09-21 through 2026-10-19 inclusive**, joined to
`log/settlements.csv` on `(date, city)` with a matching mode. Roughly 30 cities × 29
days, minus unlisted markets and unresolved days.

**Minimum for a reading: 150 joined city-days.** Below that the analysis prints its own
underpowered warning and no conclusion is drawn, whatever the numbers look like.

## Hypotheses

- **H_priced** — the market prices the skew. The paired gap `cum_dn2 − cum_up2` is
  positive and of the same order as the realized gap (~3.3 points).
- **H_flat** — the market quotes the two sides alike. The paired gap is near zero
  while the realized gap is not.

## Primary statistic and decision rule — fixed in advance

Let **D** = mean over joined city-days of `cum_dn2 − cum_up2`, in percentage points,
with its paired standard error, and let **R** = realized `P(dev ≤ −2) − P(dev ≥ +2)`
over the same rows.

| observed | conclusion |
|---|---|
| **D ≥ 2.0 pts** with t > 2 | supports **H_priced** — the skew is in the book; nothing to trade |
| **D ≤ 0.8 pts**, and R ≥ 2.0 pts on the same rows | supports **H_flat** — a real pricing gap on the cold side |
| anything between, or R < 2.0 pts | **inconclusive** — extend one further month, thresholds recomputed, decide then |

Paired, on the same city-day, deliberately: it removes the day-to-day variation in
overall uncertainty, which is large and is not what is being tested.

**R < 2.0 pts is a stop, not a pass.** If the realized asymmetry does not reproduce in
the window, the 242-row finding was noise and the pricing question is moot. That
branch is the one most likely to be rationalized away later, so it is written here.

## What a supported H_flat would and would not license

Would: a paper-traded, logged, un-sized forward test of selling `mode+2` in preference
to `mode−2` at comparable prices — the hot side, which is the *safer* one.

Would **not**: resuming the +2 board, or any size at all. The strategy failed on
adverse selection, and a directional finding about the shape of the distribution does
not repair a selector that picks rows where the market disagrees with `bt_daily`. Any
rule built on this must select on *price relative to measured risk on the whole field*,
not on a multiple over `bt_daily` tails.

## Known weaknesses, stated before the result

1. **Clustering.** 30 cities over 29 days are not 870 independent draws; one synoptic
   pattern reaches Amsterdam, Helsinki and Warsaw together. The per-city breakdown is
   reported with every run, and a result carried by one or two stations is treated as
   inconclusive regardless of D.
2. **The bottom rung.** `cum_dn2` often includes an open-ended "N°C or below" bucket
   whose implied probability covers an unbounded range, while the top rung does the
   same upward. Both ends are flagged (`top_open`, `bot_open`) but not adjusted, and
   the asymmetry in how far each open end reaches is a genuine confound. If the
   reading lands near a threshold, this is the first thing to re-cut on.
3. **Seasonality.** The window is late September to mid-October in the northern
   hemisphere. The 242-row skew was measured mostly in September. A skew that is real
   but seasonal would show here and fail in April.
4. **Direction of comfort.** H_flat is the interesting answer and the one that gives a
   dead project something to do. That is where wishful reading lives, which is why D
   has a number attached to it today.
5. **Liquidity.** A gap that exists only at a bid with $40 behind it is not a trade.
   Depth is captured per side; any conclusion is re-read on rows with ≥ $600 on both.

## Companion measurement, not decided here

Calibration of each side against its own implied value is reported at the same time.
It is the more direct question — does `cum_up2` predict `dev ≥ 2` — but it is far
weaker at this sample size than the paired comparison, so it is recorded and not ruled
on.

## Outcome

_To be completed after 2026-10-19. Leave blank until then._

- Joined city-days observed:
- D (paired price gap):
- R (realized gap):
- Per-city breakdown:
- Conclusion under the rule above:
