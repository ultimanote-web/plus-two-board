#!/usr/bin/env python3
"""
analyze_asymmetry.py — does the market price the left skew?

The risk side is measured (2026-09-19, n = 242 settled city-days):

    P(dev >= +2) = 3.72%    P(dev <= -2) = 7.02%    ratio 1.89x

This asks the other half: what does the book charge for each side, and does the
difference between the two prices match the difference between the two risks.

    python3 research/analyze_asymmetry.py

Reads log/ladders.csv (prices at decision time) and log/settlements.csv (outcomes),
joins on (date, city), and reports three things:

  1. Calibration per side — implied against realized, each with a Wilson interval.
  2. The paired price asymmetry — cum_dn2 - cum_up2 on the same city-day, which
     removes the day-to-day variation in overall uncertainty and is far tighter than
     comparing two unpaired means.
  3. Sale economics at the quoted bids, using the realized rates rather than the
     measured tails, since the whole point of 2026-09-19 was that the tails are the
     thing under suspicion.

Nothing here is a trading rule. It is a measurement, and it needs roughly 150 joined
city-days before its intervals are narrow enough to separate 3.7% from 7.0%.
"""
import csv, math, os, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEE = 0.05          # weather_fees, taker side only; makers pay zero


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - r) / d), min(1.0, (c + r) / d)


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load(path, key):
    if not os.path.exists(path):
        sys.exit(f"missing {path}")
    out = {}
    for r in csv.DictReader(open(path)):
        out[(r["date"], r["city"])] = r
    if not out:
        sys.exit(f"{path} is empty")
    return out


def sale(bid, risk):
    """Sell the bucket's YES at `bid`. Wins `bid - fee` if the bucket does not hit,
    loses `(1 - bid) + fee` if it does. Returns (break-even risk, EV per $ at risk)."""
    fee = FEE * min(bid, 1 - bid)
    profit, cost = bid - fee, (1 - bid) + fee
    if profit <= 0 or cost <= 0:
        return None, None
    be = profit / (profit + cost)
    ev = ((1 - risk) * profit - risk * cost) / cost
    return be, ev


def main():
    lp = os.path.join(ROOT, "log", "ladders.csv")
    if not os.path.exists(lp):
        print("log/ladders.csv does not exist yet — capture_ladders.py has not run.\n"
              "This is the expected state before the first capture, not a failure.")
        return
    lad = load(lp, None)
    set_ = load(os.path.join(ROOT, "log", "settlements.csv"), None)

    rows = []
    for k, L in lad.items():
        S = set_.get(k)
        if not S:
            continue
        dev = fnum(S.get("dev"))
        if dev is None:
            continue
        # the mode must agree, or the two files describe different books
        if fnum(L.get("mode")) is not None and fnum(S.get("mode")) is not None \
           and fnum(L["mode"]) != fnum(S["mode"]):
            continue
        rows.append((k, L, dev))

    n = len(rows)
    if n == 0:
        print("no joined city-days yet — capture_ladders.py has not overlapped the "
              "settlement log.\nNothing to report; expected until the first captured "
              "day settles.")
        return

    print(f"# Asymmetry pricing — {n} joined city-days\n")

    # ---- 1. calibration, each side -------------------------------------------
    print("## Calibration\n")
    print("| side | mean implied | realized | 95% CI | n |")
    print("|---|---|---|---|---|")
    for label, col, hit in (("hot  P(>= mode+2)", "cum_up2", lambda d: d >= 2),
                            ("cold P(<= mode-2)", "cum_dn2", lambda d: d <= -2)):
        vals = [(fnum(L[col]), dev) for _, L, dev in rows if fnum(L.get(col)) is not None]
        if not vals:
            continue
        imp = sum(v for v, _ in vals) / len(vals)
        k = sum(1 for _, d in vals if hit(d))
        lo, hi = wilson(k, len(vals))
        flag = "" if lo <= imp <= hi else "   <-- implied outside the interval"
        print(f"| {label} | {imp*100:.2f}% | {k/len(vals)*100:.2f}% ({k}/{len(vals)}) "
              f"| [{lo*100:.1f}, {hi*100:.1f}] |{len(vals)}|{flag}")

    # ---- 2. the paired price asymmetry ---------------------------------------
    pairs = [(fnum(L["cum_dn2"]) - fnum(L["cum_up2"]))
             for _, L, _ in rows
             if fnum(L.get("cum_dn2")) is not None and fnum(L.get("cum_up2")) is not None]
    if len(pairs) > 2:
        m = sum(pairs) / len(pairs)
        sd = math.sqrt(sum((x - m) ** 2 for x in pairs) / (len(pairs) - 1))
        se = sd / math.sqrt(len(pairs))
        print(f"\n## Paired price asymmetry\n")
        tstr = f"{m/se:+.2f}" if se > 0 else "—"
        print(f"mean(cum_dn2 - cum_up2) = {m*100:+.2f} pts,  se {se*100:.2f},  "
              f"t = {tstr},  n = {len(pairs)}")
        print("\nRealized asymmetry over the same rows: ", end="")
        kh = sum(1 for _, _, d in rows if d >= 2)
        kc = sum(1 for _, _, d in rows if d <= -2)
        print(f"{kc}/{n} cold against {kh}/{n} hot = {(kc-kh)/n*100:+.2f} pts")
        print("\nIf the paired price gap is materially smaller than the realized gap, "
              "the cold side is\nunderpriced as a *risk* — which means selling it is "
              "dearer than it looks, not cheaper.")

    # ---- 3. sale economics at the quoted bids --------------------------------
    print("\n## Selling the exact +2 and -2 buckets at the quoted bid\n")
    print("Realized rates on these rows are used as the risk, not the bt_daily tails.")
    print("\n| side | rows with a bid | mean bid | break-even | realized risk | EV/$ |")
    print("|---|---|---|---|---|---|")
    for label, bidcol, hit in (("mode+2", "bid_up2", lambda d: d >= 2),
                               ("mode-2", "bid_dn2", lambda d: d <= -2)):
        vals = [(fnum(L[bidcol]), dev) for _, L, dev in rows
                if fnum(L.get(bidcol)) not in (None, 0.0)]
        if not vals:
            print(f"| {label} | 0 | | | | |")
            continue
        mb = sum(b for b, _ in vals) / len(vals)
        risk = sum(1 for _, d in vals if hit(d)) / len(vals)
        be, ev = sale(mb, risk)
        print(f"| {label} | {len(vals)} | {mb:.3f} | "
              f"{be*100:.1f}% | {risk*100:.1f}% | {ev:+.3f} |" if be is not None
              else f"| {label} | {len(vals)} | {mb:.3f} | — | {risk*100:.1f}% | — |")

    # ---- per-city, so one station cannot carry the result --------------------
    per = defaultdict(lambda: [0, 0, 0])
    for (_, city), _, dev in rows:
        per[city][0] += 1
        per[city][1] += 1 if dev >= 2 else 0
        per[city][2] += 1 if dev <= -2 else 0
    worst = sorted(per.items(), key=lambda kv: -(kv[1][1] + kv[1][2]))[:8]
    if any(v[1] + v[2] for _, v in worst):
        print("\n## Where the tail events came from\n")
        print("| city | days | hot | cold |")
        print("|---|---|---|---|")
        for c, (d_, h, cd) in worst:
            if h + cd:
                print(f"| {c} | {d_} | {h} | {cd} |")
        print("\nA result carried by one or two cities is a station finding, not a "
              "distributional one.")

    if n < 150:
        print(f"\n> **Underpowered.** {n} joined city-days. Separating 3.7% from 7.0% "
              f"at 95%\n> needs roughly 150. Read the direction, not the decision.")


if __name__ == "__main__":
    main()
