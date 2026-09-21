# Result — there are no calm cities

**Run 2026-09-21 against `log/settlements.csv` (349 settled city-days, 38 cities) and the
first captured field in `log/ladders.csv`.**

The question asked: can the board select the cities whose actual high is least likely to
exceed the forecast high? The answer is that the question has no answer at the city
level, because cities do not differ.

---

## 1. The per-city rates are one rate

`hit = 1` when `actual − market mode ≥ 2`. Field: **14 hits in 349 city-days = 4.01%**.

Distribution of per-city hit counts, against what a single common 4.01% rate predicts
over the same per-city day counts:

| hits | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| cities observed | 27 | 9 | 1 | 1 |
| expected if homogeneous | 26.3 | 9.9 | 1.7 | 0.2 |

| | |
|---|---|
| χ² against one common rate | 43.3 on 37 df |
| Monte-Carlo P(χ² ≥ observed \| homogeneous) | **0.245** |
| worst city | karachi, 3 hits in 10 days |
| P(some city reaches ≥ 3 by chance) | **0.181** |

There is no city-level signal here. Not a weak one — none. The observed spread is what
38 coin-flips at one rate look like.

**This includes the exclusions.** Shenzhen (2 hits) and Karachi (3) are both inside what
chance produces across 38 cities, and `exclusions.json` is therefore selecting noise. It
stays in place, because the cost of excluding two cities from a halted board is zero and
the review dates are already set, but it should not be described as a finding. Recorded
here so that the next person to read `STATUS.md` does not mistake it for one.

## 2. No available risk measure orders the outcomes

Spearman rank correlation between each station-level measure and that city's realized
+2 rate, over cities with ≥ 5 settled days (n = 37):

| measure | ρ | t |
|---|---|---|
| `bt_daily` exact-bucket tail (`p_eq2`) | −0.048 | −0.29 |
| `bt_daily` cumulative tail (`p_ge2`) | −0.198 | −1.20 |
| forecast-native `resid_ge2_share` | +0.071 | +0.42 |
| residual sd | +0.027 | +0.16 |
| residual p90 | +0.060 | +0.36 |

All within noise. The forecast-native measure, which the tail adjudication just
vindicated as the better *estimate*, is no better as a *selector* — it points the right
way (terciles 5.3% / 3.9% / 2.8%) but at t = 0.42 that ordering is indistinguishable
from the one `bt_daily` gets backwards.

Being a less wrong estimate of a quantity that does not vary is not worth anything.

## 3. What does vary is days, and the market already prices them

The first captured field, 38 cities for trading day 2026-09-21, snapshot
2026-09-20T09:28 UTC:

| | |
|---|---|
| mean implied P(≥ mode+2) | **7.99%** |
| median implied | **3.90%** |
| range across the field | 0.1% to 27.3% |
| realized field rate over 349 days | 4.01% [2.4–6.6] |

The median row is priced almost exactly at the realized field rate. The mean is dragged
up by a handful of rows priced at 20–27%. That spread is not the market disagreeing
about which *cities* are risky — §1 says cities are the same — it is the market pricing
which *days* are unsettled. Sao Paulo at 27% is not "Sao Paulo is a hot-tail station";
it is "tomorrow in Sao Paulo is uncertain".

## 4. The trap, stated explicitly

Given §1, the tempting move is to treat every row as carrying the same 4.01% risk and
sell whichever +2 bucket pays most. Ranked that way, today's field looks like this:

| city | bid | break-even | implied | EV/$ at 4.01% |
|---|---|---|---|---|
| sao-paulo | 0.200 | 19.0% | 27.3% | +0.185 |
| shenzhen | 0.190 | 18.1% | 24.7% | +0.171 |
| chengdu | 0.190 | 18.1% | 21.7% | +0.171 |
| chongqing | 0.180 | 17.1% | 26.2% | +0.158 |
| qingdao | 0.130 | 12.3% | 18.8% | +0.095 |

**This is the original failure, verbatim.** The rule "sell where break-even exceeds my
risk estimate" selects exactly the rows where the market says the risk is 25% and the
model says 4%. That is the same disagreement-selector that produced 6 of 34 selected
rows settling at +2 against 1.3 expected, with `bt_daily` in the role now being offered
to the field average.

§1 established that cities do not differ *averaged over all days*. It established
nothing about whether tomorrow in Sao Paulo is a 4% day. Applying a field average to the
row the market has singled out as unsettled is the identical error with a new number in
it.

## 5. The question that is actually open

Is the market's implied probability calibrated? Not "is it right about cities" — it is
about days, and the only way to know is to ask whether rows priced at 20% hit at 20%.

That needs paired prices and outcomes across a range of implied values, which is what
`log/ladders.csv` began collecting on 2026-09-20 and what
`research/prereg-asymmetry-pricing.md` already registers thresholds for. The calibration
reading is a by-product of that window and is reported by `analyze_asymmetry.py` with
every self-check.

One number worth watching, and worth **not** acting on yet: mean implied 7.99% against a
realized field rate of 4.01%. If that gap survives a registered window it implies the
whole field is dear, and selling it *indiscriminately* — every row, no gate, no estimate
— would be the one rule that cannot select adversely, because it does not select. If it
does not survive, it was the high-priced tail dragging a mean, which is §4 wearing a
different hat.

---

## What this changes

- **City selection is dead.** Not "needs a better tail" — there is nothing at the city
  level to select on. Any future rule must operate per day, not per station.
- **The tail adjudication's win is narrower than it looked.** `bt_daily` is wrong at
  those seven stations, and replacing it buys nothing on its own.
- **The exclusions are noise**, kept for zero cost, not to be cited as evidence.
- **The board stays halted.** Nothing here is a licence, and §4 exists so that the next
  idea gets tested before it gets traded rather than after.
