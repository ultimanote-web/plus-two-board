# Pre-registration — is the late-day residual price too high?

**Registered 2026-09-21, before `log/intraday.csv` exists.**
Committed to git as the timestamp. Nothing below may be changed once the first row
lands; a revision is a new registration with its own date, and both stay in the repo.

---

## The question

Everything this project has measured says the market is calibrated **at board horizon**,
roughly 30 hours before resolution. `research/gate-value.md`: 252 tradable rows, realized
rate tracking break-even across every price band, whole-field P/L −0.15% per dollar
risked with a bootstrap CI of [−1.68%, +1.52%].

That is a claim about T−30h. It is not a claim about T−11h.

Inside the local afternoon the situation is different in kind. Most of the day's heating
has already happened and **the current reading is observable**. On 2026-09-21 the
Qingdao 30 °C bucket was quoted 13.1% in the morning capture and 3.8% eleven hours
before resolution; Wuhan 27 °C went 23.8% → 7.6%. The market clearly re-prices as the
day develops. The open question is whether the *residual* is right, or whether prices
lag a collapsing uncertainty.

This is the only hypothesis this project has entertained that rests on a physical
mechanism — a bounded heating cycle, partly complete, directly measurable — rather than
on a pattern fitted to a handful of events. That is a reason to test it carefully, not a
reason to believe it.

## Hypotheses

- **H_null** — the late-day price is calibrated, exactly as the board-horizon price is.
  Buckets quoted at *p* late in the day settle at *p*.
- **H_lag** — the late-day price is systematically too high on far buckets. Realized
  rates come in materially below the break-even the quotes imply.

## Data

`selfcheck/capture_intraday.py`, added 2026-09-21, runs at 00/06/12/18 UTC and records
for every city, keyed to that city's **own local date**:

- the full ladder, and the usual mode / `cum_up2` / `cum_dn2` / bid / depth summary
- **`obs_max`** — the day's maximum observed so far at the resolving ICAO, from METAR
- `obs_latest`, `wind_dir`, `wind_kt`, `precip_mm`, `cloud_pct`, `local_hour`
- **`hours_to_sunset`**, and **`headroom_up2`** = (mode + 2) − `obs_max`, the number of
  degrees the temperature still has to climb for the +2 bucket to hit

`obs_source` distinguishes `metar` (the station's own reading) from
`open_meteo_model` (model output for past hours). **Rows with `obs_source` other than
`metar` are excluded from the primary test.** This project has already been bitten once
by treating a model value as a station reading, and the entire hypothesis is about
observation.

## Cohort — fixed now

One row per city-day: the capture whose `hours_to_sunset` is **closest to 3.0**, and
only if that value falls in **[1.0, 5.0]**. Several captures of the same city-day are
not independent observations, and taking the best of them is the error this whole
project exists to avoid.

A row qualifies when all of:

- `obs_source == "metar"` and `obs_n >= 6`
- `hours_to_sunset` in [1.0, 5.0]
- `bid_up2 > 0` and `depth_up2 >= 300`
- the city-day appears in `log/settlements.csv` with a resolved actual
- the city is not in `exclusions.json`

**Window: trading days 2026-09-23 through 2026-10-31 inclusive.**
**Minimum for a reading: 800 qualifying city-days.** Below that, no conclusion is drawn
whatever the numbers look like.

## Primary statistic and decision rule — fixed in advance

For each qualifying row, the quoted `bid_up2` implies a break-even
`B = profit / (profit + cost)` with `fee = 0.05 × min(bid, 1−bid)`. Let **E** be the
mean of `B` across the cohort and **A** the realized rate of `dev ≥ +2`, with a 95%
Wilson interval.

| observed | conclusion |
|---|---|
| Wilson **upper** bound of A < E, **and** A ≤ 0.5 × E | supports **H_lag** — a real late-day overpricing |
| Wilson interval of A contains E | supports **H_null** — calibrated late as well as early |
| anything else | **inconclusive** — extend one month, thresholds recomputed, decide then |

Both conditions are required for H_lag on purpose. A statistically significant 0.2-point
gap is not a tradable one at 25:1 payoffs; requiring the realized rate to be half the
implied rate is what separates "detectable" from "worth the tail risk".

**Reported alongside, decided by nobody:** the same calculation on `bid_dn2` (the cold
side), and the P/L per dollar risked with a day-clustered bootstrap. These are context,
not tests, and no decision is taken on them in this registration.

## Secondary measurement — recorded, not decided

Does `headroom_up2` carry information **beyond** the price? Within bands of quoted
`bid_up2`, does a larger required climb predict a lower hit rate?

This is the question that decides whether there is an edge *of ours* rather than a
market inefficiency anyone could harvest. It is also badly underpowered at one month, so
it is reported each week and ruled on at no point in this registration.

## What this does NOT license

- **It does not unhalt the board.** The board is a T−30h selector and nothing here
  concerns it.
- **It does not license size.** If H_lag is supported, the honest next step is a
  logged, minimum-size forward test with a written rule, not a scaling decision. The
  payoff shape here — risking 96¢ to make 4¢ — means a strategy can be wrong by two
  percentage points and still win nineteen times out of twenty on the way to losing
  money. Win rate is not evidence. Only the realized rate against break-even is.
- **The live trades in `log/trades.csv` are not the test.** They are self-selected: the
  operator chose the city, the bucket and the moment. Four wins from four choices
  cannot separate skill from a 96% base rate, and a self-selected sample cannot
  adjudicate a pricing question at all. It is logged because entry price and timing are
  worth keeping, and because the alternative is screenshots.

## Known weaknesses, stated before the result

1. **Clustering.** 38 cities are not 38 independent draws on a given day; a single
   synoptic pattern covers several. The day-clustered bootstrap is reported with the
   primary statistic, and a result driven by fewer than five distinct dates is treated
   as inconclusive regardless.
2. **The tail is the whole risk.** At these prices the events that matter are rare and
   arrive on days that look benign — a late foehn, a heat burst, a delayed station
   correction. One month may contain none of them and still not be evidence of safety.
   H_lag being supported over 800 rows with, say, four events is a weak result wearing
   a large denominator; the event count is reported prominently for exactly that reason.
3. **Resolution source — the sharpest weakness.** The markets resolve on a published
   station timeseries (`weather.gov/wrh/timeseries?site=<icao>` for the stations checked
   so far), **not** on aviationweather.gov. Both are fed by the same METAR stream for an
   ICAO and ought to agree, but at 1 °C buckets a rounding, units-conversion or
   late-correction difference is the entire trade. `analyze_late_day.py` therefore
   reports the agreement rate between the METAR maximum and the settled bucket with
   every run. **An apparent edge smaller than the observed proxy error is not an edge**,
   and if agreement runs below roughly 95% the primary test is reported but not acted
   on, whatever it says.

   Note also for anyone reading a chart by eye: Weather Underground serves personal
   weather stations alongside airport stations, and a PWS a few kilometres away can
   differ by more than a degree. Only the resolving ICAO's own page is the market.
4. **Selection at capture time.** The capture is indiscriminate by design — every city,
   every run, tradable or not — precisely because the board's downfall was a price
   sample conditioned on the selector.
5. **Direction of comfort.** H_lag is the interesting answer and the one that gives a
   halted project something to do. That is where wishful reading lives, which is why E,
   A and the 0.5 ratio are written down today.

## Outcome

_To be completed after 2026-10-31. Leave blank until then._

- Qualifying city-days observed:
- Distinct dates:
- Mean implied break-even (E):
- Realized rate (A), events / n, 95% Wilson:
- P/L per $ risked, day-clustered CI:
- Cold side (context):
- Conclusion under the rule above:
