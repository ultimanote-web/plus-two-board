# Result — the model adds nothing to the market's mode

**Run 2026-09-19 against `log/settlements.csv`.** Specification fixed before the data was
touched; the pre-committed reading is quoted below before the numbers.

---

## 1. Does the model–market gap predict anything? No.

`gap = market mode − de-biased Open-Meteo forecast`. `dev = actual − market mode`.

If the model is right and the market's mode is noise, `actual ≈ forecast`, so `dev ≈ −gap`
— slope **−1**. If the market's mode already contains the model, slope **0**.

> Pre-committed: slope ≤ −0.5 with |t| > 2 is a real signal; slope near 0 means the
> market's mode already contains the model.

**Result, n = 178 settled city-days carrying a gap:**

```
slope     −0.043
se         0.064
t         −0.67
r         −0.05
```

Not a weak signal — nothing. And it is not a linearity problem; in the region where the
effect should have been strongest, the sign is wrong:

| gap | n | predicted dev | observed dev |
|---|---|---|---|
| < −2 | 10 | **+3.1** | **−0.30** |
| −2 to −1 | 16 | +1.4 | −0.13 |
| −1 to −0.5 | 16 | +0.8 | −0.06 |
| −0.5 to +0.5 | 63 | 0.0 | +0.10 |
| +0.5 to +1 | 33 | −0.6 | −0.27 |
| +1 to +2 | 36 | −1.3 | −0.28 |
| > +2 | 4 | −2.5 | −0.50 |

There is faint directional agreement on the positive-gap side at roughly a fifth of the
predicted magnitude, and none at all on the negative side. Zhengzhou on 17 September —
gap −4.6, actual +3 above the mode — was the row that prompted this test by eye. The bin
it belongs to averages **−0.30**. That gap is the entire argument for testing rather than
reading rows.

## 2. Is the market's modal bucket correctly priced? Yes, to within half a point.

Same 178 rows:

| | |
|---|---|
| actual landed on the market's modal bucket | **46.1%** |
| market's mean implied probability for that bucket | **45.7%** |
| 95% CI on the realized rate | [38.8, 53.4] |
| mean `dev` | **−0.12 °C** |

The implied value sits in the centre of the interval. At this power a mispricing of about
±7 points would have been visible; there is none. The market's mode is calibrated and
unbiased.

## 3. Why the original strategy failed

Not the gates, and not the season — the field settles **calmer** than the backtest
(3.4% realized against 7.5% predicted, t = −2.16, n = 207), which is the opposite of a
late-season-uncertainty story, and the snapshot window is already centred on day-of-year
274 ± 45 days.

The mechanism is **adverse selection, built into the selection rule**. The multiple is
`break-even ÷ measured tail`, required above 1 — which selects exactly the rows where the
price implies more risk than `bt_daily` does. Every selected row is a row where we
disagreed with the market. The settlements say the market was right:

| | rate on selected rows |
|---|---|
| `bt_daily` predicted | 3.8% |
| the prices implied | ~4–11% |
| realized | **22%** (4 of 18) |

No gate can repair this, because the gate *is* the selector. Tightening a threshold picks
a smaller subset of the same disagreement. It also explains the inverted tail terciles:
high-tail stations are where `bt_daily` overstates risk, so they never clear the filter
and never lose; low-tail stations are where it understates, so they always clear, and that
is where the losses land.

The load-bearing assumption was that a 192-day seasonal backtest estimates tomorrow's risk
better than a market with real money in it. Over 207 city-days it did not.

---

# Result — the distribution is asymmetric, and the cold side is the risky one

Full log, **n = 242 settled city-days**, `dev = actual − market mode`:

| dev | −5 | −4 | −3 | −2 | −1 | 0 | +1 | +2 | +3 |
|---|---|---|---|---|---|---|---|---|---|
| count | 1 | 1 | 5 | 10 | 46 | 115 | 55 | 8 | 1 |

| | |
|---|---|
| **P(dev ≥ +2)** — the hot tail | **3.72%** [2.0–6.9], 9/242 |
| **P(dev ≤ −2)** — the cold tail | **7.02%** [4.4–11.0], 17/242 |
| ratio cold ÷ hot | **1.89×** |
| skew | **−0.89** |
| mean | −0.07 °C |

**The ±1 buckets are symmetric** — 64 hot against 63 cold. The asymmetry is entirely in
the tails, and it deepens with distance:

| tail | hot | cold | P(this lopsided \| symmetric) |
|---|---|---|---|
| ±2 | 9 | 17 | 8.4% one-sided |
| ±3 | 1 | 7 | 3.5% one-sided |

Beyond +3 the distribution simply stops — one observation in 242. The cold side reaches
−5.

**So +2 is the more consistent side, by roughly two to one.** Selling the `mode−2` NO —
betting the day does not come in that cold — is the *worse* trade of the two at equal
prices, not the better one.

There is a physical reason to expect this rather than a data artifact: a daily maximum is
bounded above by clear-sky insolation, which is a hard ceiling on any given date, but it
can be dragged far below by cloud, rain or cold advection. A left-skewed maximum is what
the physics predicts, and −0.89 is what the data shows.

**Caveat on power.** 8.4% one-sided at ±2 is suggestive, not established. The ±3 result is
firmer but rests on 8 events. Both come from the same 242 rows that generated every other
finding here, so this is an observation to pre-register and test forward, not a result to
trade.

**What is not yet measured:** whether the market *prices* the asymmetry. If `mode−2` and
`mode+2` are quoted at similar prices while their true risks are 7.0% and 3.7%, that is a
real mispricing; if the market already quotes the cold side richer, there is nothing here.
A ladder capture was in progress when the browser connection dropped. **This is the open
question and it is the cheap one to answer** — it needs one batch of live ladders and a
comparison of `price(mode−2)` against `price(mode+2)`.

**Answered by measurement, not by one batch.** A single hand-captured day would have been
a sample of one afternoon's book, and it would have been captured by whoever happened to
be looking — which is how the adverse selection above got in. Instead
`selfcheck/capture_ladders.py` now records the whole ladder for the whole field on every
board run, `research/analyze_asymmetry.py` reports it with every self-check, and
`research/prereg-asymmetry-pricing.md` fixes the thresholds before the first row exists.
The reading is due **2026-10-19** at 150 joined city-days. Nothing is traded on it either
way; the +2 board stays halted.

---

## What survives

- **Gap trading** — dead. Slope −0.04.
- **Mode mispricing** — dead. 46.1% against 45.7% implied.
- **Tail asymmetry** — open, and the only directional idea with evidence behind it.
  Needs the pricing half before it means anything.
- **Market making** — untouched by all of this. Weather markets are `takerOnly: true`
  (makers pay zero), `rebateRate 0.25`, liquidity rewards at `rewardsMaxSpread 4.5`,
  `rewardsMinSize 50`. It requires no forecast edge at all, which after the above is a
  point in its favour.

## What this cost and what it bought

Five losing selected rows and about ten days. In exchange: a settlement log, an automated
self-check that raised the field warning on its own, a pre-registration that is about to
be read at thresholds fixed before its data existed, and three hypotheses closed in one
afternoon that would otherwise have been closed by months of losses.

The apparatus worked. The strategy did not.
