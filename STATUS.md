# HALTED

_self-check 2026-09-12T17:55:56+00:00_

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

## Manual exclusions

- **shenzhen** — two +2 settlements in three days, both exact (review by 2026-10-10)

## Pipeline

- inputs 0.0 h old, snapshot `d97b44c4b5f2`, 38 stations / 38 tails

## Warnings

- ordering: the low-tail band produced more +2 settlements than the high-tail band — the score's primary parameter has not demonstrated discrimination; do not tighten anything on it yet
- no predictions/2026-09-11.json — either no board was built for that day, or it was built and never logged. An unlogged board cannot be checked.

---

At this sample size these checks catch a broken risk model, not a mediocre one.
A green run is not evidence the strategy works.
