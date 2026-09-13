# HALTED

_self-check 2026-09-13T18:37:16+00:00_

## Do not trade the next board

- selected rows: 3 of 7 settled at +2 against 0.35 expected — P(>=3 | tails correct) = 0.37%, below the 2% halt threshold
- shenzhen: settled at +2 twice within 14 days (2026-09-10 and 2026-09-12) — treat as station-specific until explained

## Selected rows

- 3 of 7 settled at +2 (43%), against 0.35 expected
- P(>= 3 | tails correct) = 0.37%
- 95% CI on the realized rate: 16-75%

## Whole field

- 5 of 74 at >=+2 (6.8%) against 7.0% predicted, t = -0.07

## Does the tail order the outcomes?

| band | range | n | hits | expected |
|---|---|---|---|---|
| low | 2.1-4.7% | 24 | 2 | 0.82 |
| mid | 4.7-7.3% | 24 | 2 | 1.48 |
| high | 7.3-15.7% | 26 | 1 | 2.87 |

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

## Pipeline

- inputs 14.4 h old, snapshot `d97b44c4b5f2`, 38 stations / 38 tails

## Warnings

- ordering: the low-tail band produced more +2 settlements than the high-tail band — the score's primary parameter has not demonstrated discrimination; do not tighten anything on it yet
- tail may be UNDERSTATED at chengdu (7.8% vs 15.0%), kuala-lumpur (8.3% vs 14.0%) — these rows can be selected while carrying more risk than scored
- tail may be OVERSTATED at singapore (10.4% vs 1.0%), amsterdam (14.7% vs 1.6%), helsinki (13.0% vs 1.6%), beijing (13.0% vs 2.1%), toronto (14.7% vs 3.1%) — the board may be excluding rows that are not actually risky

---

At this sample size these checks catch a broken risk model, not a mediocre one.
A green run is not evidence the strategy works.
