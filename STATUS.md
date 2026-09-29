# HALTED

_self-check 2026-09-29T20:10:52+00:00_

## Do not trade the next board

- selected rows: 8 of 60 settled at +2 against 2.33 expected — P(>=8 | tails correct) = 0.22%, below the 2% halt threshold
- shenzhen: settled at +2 twice within 14 days (2026-09-10 and 2026-09-12) — treat as station-specific until explained
- karachi: settled at +2 twice within 14 days (2026-09-12 and 2026-09-14) — treat as station-specific until explained
- zhengzhou: settled at +2 twice within 14 days (2026-09-17 and 2026-09-21) — treat as station-specific until explained
- ankara: settled at +2 twice within 14 days (2026-09-18 and 2026-09-22) — treat as station-specific until explained
- cape-town: settled at +2 twice within 14 days (2026-09-25 and 2026-09-26) — treat as station-specific until explained
- lucknow: settled at +2 twice within 14 days (2026-09-26 and 2026-09-28) — treat as station-specific until explained

## Selected rows

- 8 of 60 settled at +2 (13%), against 2.33 expected
- P(>= 8 | tails correct) = 0.22%
- 95% CI on the realized rate: 7-24%

## Whole field

- 26 of 642 at >=+2 (4.0%) against 7.5% predicted, t = -3.20

## Does the tail order the outcomes?

| band | range | n | hits | expected |
|---|---|---|---|---|
| low | 2.1-4.7% | 214 | 9 | 7.91 |
| mid | 4.7-8.3% | 214 | 13 | 15.06 |
| high | 8.3-25.1% | 214 | 4 | 25.29 |

## Two estimates of the same risk disagree

`bt_daily` bucket tail vs the forecast-native share of days the actual came
in >= 2 C above the de-biased forecast. Bucket rounding puts the native figure
somewhat lower by construction, so only gross divergence is listed.

| city | bucket tail | forecast-native | ratio | |
|---|---|---|---|---|
| chengdu | 7.8% | 15.0% | 1.92x | understated |
| kuala-lumpur | 8.3% | 14.0% | 1.68x | understated |
| manila | 12.7% | 3.6% | 0.29x | overstated |
| warsaw | 13.1% | 3.1% | 0.24x | overstated |
| toronto | 14.7% | 3.1% | 0.21x | overstated |
| beijing | 13.0% | 2.1% | 0.16x | overstated |
| helsinki | 13.0% | 1.6% | 0.12x | overstated |
| amsterdam | 14.7% | 1.6% | 0.11x | overstated |
| singapore | 10.4% | 1.0% | 0.10x | overstated |

## Manual exclusions

- **shenzhen** — two +2 settlements in three days, both exact (review by 2026-10-10)
- **karachi** — repeat +2 settlements against a 3.8% tail; flagged by check.py since 2026-09-15 and left unactioned for a week (review by 2026-10-17)

## Pipeline

- inputs 15.9 h old, snapshot `d97b44c4b5f2`, 38 stations / 38 tails

## Warnings

- field: predicted 7.5% sits above the realized interval [2.8-5.9] — tails may be too conservative
- ordering: the low-tail band produced more +2 settlements than the high-tail band — the score's primary parameter has not demonstrated discrimination; do not tighten anything on it yet
- tail may be UNDERSTATED at chengdu (7.8% vs 15.0%), kuala-lumpur (8.3% vs 14.0%) — these rows can be selected while carrying more risk than scored
- tail may be OVERSTATED at singapore (10.4% vs 1.0%), amsterdam (14.7% vs 1.6%), helsinki (13.0% vs 1.6%), beijing (13.0% vs 2.1%), toronto (14.7% vs 3.1%) — the board may be excluding rows that are not actually risky

---

At this sample size these checks catch a broken risk model, not a mediocre one.
A green run is not evidence the strategy works.
