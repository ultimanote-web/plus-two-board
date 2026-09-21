#!/usr/bin/env python3
"""
analyze_late_day.py — reads log/intraday.csv against research/prereg-late-day-residual.md.

Implements the registered cohort rule exactly: one row per city-day, the capture whose
hours_to_sunset is closest to 3.0 and inside [1.0, 5.0], METAR-sourced only, with a
live bid and depth, joined to a resolved settlement.

Prints the primary statistic and the decision under the fixed rule, refusing to
conclude below 800 qualifying city-days. Run by the self-check; safe to run any time.
"""
import csv, json, math, os, random, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEE = 0.05
TARGET_H, H_LO, H_HI = 3.0, 1.0, 5.0
MIN_OBS, MIN_DEPTH, MIN_N = 6, 300, 800
WINDOW = ("2026-09-23", "2026-10-31")


def f(x):
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - r) / d), min(1.0, (c + r) / d)


def breakeven(b):
    fee = FEE * min(b, 1 - b)
    pr, co = b - fee, (1 - b) + fee
    return (pr / (pr + co)) if (pr > 0 and co > 0) else None


def pl(rows, bidcol, hitfn):
    tot = risked = 0.0
    for r, hit in rows:
        b = f(r[bidcol])
        if not b or b <= 0:
            continue
        fee = FEE * min(b, 1 - b)
        pr, co = b - fee, (1 - b) + fee
        tot += (-co if hitfn(hit) else pr)
        risked += co
    return (tot / risked * 100) if risked else None


def proxy_check(ip, settle):
    """How closely does the METAR maximum match what the market actually resolved on?

    The markets resolve on a published source (weather.gov's station timeseries for the
    stations checked so far), not on aviationweather.gov. Both are fed by the same METAR
    stream for an ICAO, so they ought to agree — but 'ought to' is not a measurement, and
    at 1 °C buckets a rounding or units difference is the whole trade. If the proxy is
    off by a degree on even a few percent of days, an edge smaller than that is not an
    edge, and this table is how we find out rather than assume.

    Uses the largest obs_max seen across all of a city-day's captures, which approximates
    the day's maximum as observed. Days whose last capture came before the local peak
    will understate it, so a small negative skew here is expected and is not error.
    """
    seen = defaultdict(lambda: None)
    for r in csv.DictReader(open(ip)):
        if r.get("obs_source") != "metar":
            continue
        v = f(r.get("obs_max"))
        if v is None:
            continue
        k = (r["date"], r["city"])
        if seen[k] is None or v > seen[k]:
            seen[k] = v

    diffs = defaultdict(int)
    rows = []
    for r in csv.DictReader(open(os.path.join(ROOT, "log", "settlements.csv"))):
        k = (r["date"], r["city"])
        a = f(r.get("actual"))
        if k in seen and seen[k] is not None and a is not None:
            rows.append((k, seen[k], a))
    if not rows:
        return
    for _, obs, act in rows:
        diffs[int(round(act - obs))] += 1
    tot = len(rows)
    exact = sum(v for d, v in diffs.items() if d == 0)
    print(f"\n## Proxy check — METAR max vs settled bucket ({tot} city-days)\n")
    print("| settled − METAR max | n | share |")
    print("|---|---|---|")
    for d in sorted(diffs):
        print(f"| {d:+d} °C | {diffs[d]} | {diffs[d]/tot*100:.1f}% |")
    print(f"\nExact agreement: **{exact/tot*100:.1f}%**. The markets resolve on the "
          "published station timeseries, not on this feed; anything below very high "
          "agreement means an apparent late-day edge may be proxy error rather than "
          "mispricing.")


def main():
    ip = os.path.join(ROOT, "log", "intraday.csv")
    if not os.path.exists(ip):
        print("log/intraday.csv does not exist yet — capture_intraday.py has not run.\n"
              "Expected state before the first capture, not a failure.")
        return
    sp = os.path.join(ROOT, "log", "settlements.csv")
    if not os.path.exists(sp):
        print("no log/settlements.csv"); return

    settle = {}
    for r in csv.DictReader(open(sp)):
        d = f(r.get("dev"))
        if d is not None:
            settle[(r["date"], r["city"])] = d

    excl = set()
    ep = os.path.join(ROOT, "exclusions.json")
    if os.path.exists(ep):
        excl = {e["city"] for e in json.load(open(ep)).get("cities", [])}

    # one row per city-day: the capture nearest hours_to_sunset == 3.0
    best = {}
    total = 0
    for r in csv.DictReader(open(ip)):
        total += 1
        h = f(r.get("hours_to_sunset"))
        if h is None or not (H_LO <= h <= H_HI):
            continue
        if r.get("obs_source") != "metar":
            continue
        if (f(r.get("obs_n")) or 0) < MIN_OBS:
            continue
        k = (r["date"], r["city"])
        d = abs(h - TARGET_H)
        if k not in best or d < best[k][0]:
            best[k] = (d, r)

    cohort = []
    for k, (_, r) in best.items():
        if not (WINDOW[0] <= k[0] <= WINDOW[1]):
            continue
        if k[1] in excl or k not in settle:
            continue
        b = f(r.get("bid_up2"))
        if not b or b <= 0 or (f(r.get("depth_up2")) or 0) < MIN_DEPTH:
            continue
        cohort.append((r, settle[k]))

    n = len(cohort)
    dates = sorted({r["date"] for r, _ in cohort})
    print(f"# Late-day residual — {n} qualifying city-days "
          f"({total} intraday rows, {len(dates)} distinct dates)\n")
    if n == 0:
        print("Nothing qualifies yet. Expected until the window opens "
              f"({WINDOW[0]}) and METAR-backed captures accumulate.")
        return

    bes = [breakeven(f(r["bid_up2"])) for r, _ in cohort]
    bes = [b for b in bes if b is not None]
    E = sum(bes) / len(bes)
    k = sum(1 for _, d in cohort if d >= 2)
    A = k / n
    lo, hi = wilson(k, n)

    print("| | |")
    print("|---|---|")
    print(f"| mean implied break-even (E) | **{E*100:.2f}%** |")
    print(f"| realized rate (A) | **{A*100:.2f}%** ({k}/{n}) |")
    print(f"| 95% Wilson on A | [{lo*100:.2f}, {hi*100:.2f}] |")
    print(f"| A / E | {A/E if E else float('nan'):.2f} |")
    print(f"| **events** | **{k}** |")

    p = pl(cohort, "bid_up2", lambda d: d >= 2)
    if p is not None:
        random.seed(17)
        byday = defaultdict(list)
        for r, d in cohort:
            byday[r["date"]].append((r, d))
        bs = []
        for _ in range(2000):
            pick = [random.choice(dates) for _ in dates]
            rows = [x for dd in pick for x in byday[dd]]
            v = pl(rows, "bid_up2", lambda d: d >= 2)
            if v is not None:
                bs.append(v)
        bs.sort()
        print(f"\nP/L per $ risked: {p:+.2f}%  day-bootstrap 95% CI "
              f"[{bs[int(.025*len(bs))]:+.2f}%, {bs[int(.975*len(bs))]:+.2f}%]")

    pc = pl(cohort, "bid_dn2", lambda d: d <= -2)
    kc = sum(1 for _, d in cohort if d <= -2)
    if pc is not None:
        print(f"cold side (context only): {kc} events, P/L {pc:+.2f}% per $ risked")

    print("\n## Decision under the registered rule\n")
    if n < MIN_N:
        print(f"**No conclusion.** {n} of the {MIN_N} city-days the registration "
              f"requires. Read the direction, not the decision.")
    elif len(dates) < 5:
        print(f"**Inconclusive** — only {len(dates)} distinct dates; the registration "
              f"treats that as clustering regardless of the numbers.")
    elif hi < E and A <= 0.5 * E:
        print("**H_lag supported** — the Wilson upper bound sits below the implied "
              "break-even and the realized rate is at most half of it.\n\n"
              "Per the registration this licenses a logged, minimum-size forward test "
              "with a written rule. It does not license size, and it does not unhalt "
              "the board.")
    elif lo <= E <= hi:
        print("**H_null supported** — the implied break-even sits inside the interval. "
              "Calibrated late as well as early.")
    else:
        print("**Inconclusive** under the rule. Extend one month and recompute the "
              "thresholds, as registered.")

    proxy_check(ip, settle)

    # headroom, reported and not decided
    bands = defaultdict(lambda: [0, 0])
    for r, d in cohort:
        hr = f(r.get("headroom_up2"))
        if hr is None:
            continue
        b = "<=1.0C" if hr <= 1.0 else ("1.0-2.5C" if hr <= 2.5 else ">2.5C")
        bands[b][0] += 1
        bands[b][1] += 1 if d >= 2 else 0
    if bands:
        print("\n## Headroom (recorded, not decided)\n")
        print("| climb still needed for +2 | n | hits | rate |")
        print("|---|---|---|---|")
        for b in ("<=1.0C", "1.0-2.5C", ">2.5C"):
            if b in bands:
                nn, hh = bands[b]
                print(f"| {b} | {nn} | {hh} | {hh/nn*100:.2f}% |")
        print("\nThis is the question of whether we know anything the price does not. "
              "It is underpowered by design at one month and no decision rests on it.")


if __name__ == "__main__":
    main()
