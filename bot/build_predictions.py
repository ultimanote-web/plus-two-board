#!/usr/bin/env python3
"""
build_predictions.py — run on the droplet, nightly, after export_board_inputs.py.

Writes predictions/YYYY-MM-DD.json: the DETERMINISTIC half of the board — ladders,
tails, prices, model gaps, penalties, scores, eligibility. That file is what the
self-check compares settlements against, and what the published board is written from.

It deliberately does not write prose. The verdict, the per-row note, and which row is
the day's warning rather than the day's trade are judgement, and a script that invents
them is a script inventing reasoning it cannot produce.

    python3 bot/build_predictions.py --repo /opt/plus-two-board --push

Needs outbound HTTPS to gamma-api.polymarket.com and api.open-meteo.com.
"""
import argparse, json, math, os, subprocess, sys, time, urllib.request
from datetime import datetime, timezone, date, timedelta

GAMMA = "https://gamma-api.polymarket.com/events?slug=highest-temperature-in-{city}-on-{month}-{day}-2026"
OM    = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
         "&hourly=temperature_2m,precipitation,cloud_cover"
         "&start_date={d}&end_date={d}&timezone=auto")
MONTHS = ["january","february","march","april","may","june",
          "july","august","september","october","november","december"]

# Scoring weights. Declared, not fitted. Frozen until the settlement log can estimate
# them — which is the entire reason the log exists.
W_POP, W_PRICE = 2.0, 1.0
PEN_KSTAR, PEN_MODE_CAP, PEN_GAP_CAP, PEN_CEIL, PEN_SMALL_N = 25, 20, 30, 20, 5
MODE_FLOOR, GAP_FLOOR, CEIL_MULT, MIN_N, MIN_DEPTH = 0.35, 1.0, 2.5, 175, 600
FEE = 0.05
WINDOW = (11, 17)


def get(url, tries=3, pause=0.3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                time.sleep(pause)
                return json.loads(r.read().decode())
        except Exception as e:
            if i == tries - 1:
                print(f"  ! {url.split('?')[0]}: {e}", file=sys.stderr)
                return None
            time.sleep(2 * (i + 1))


def wilson(p, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pct_rank(vals, v):
    n = len(vals)
    below = sum(1 for x in vals if x < v)
    eq = sum(1 for x in vals if x == v)
    return 100.0 * (below + 0.5 * eq) / n


def bucket_num(title):
    digits = ""
    for ch in title:
        if ch.isdigit() or (ch == "-" and not digits):
            digits += ch
        elif digits:
            break
    return int(digits) if digits else None


def read_ladder(city, d):
    ev = get(GAMMA.format(city=city, month=MONTHS[d.month - 1], day=d.day))
    if not ev:
        return None
    e = ev[0]
    ms = e.get("markets", [])
    if len(ms) < 5:
        return None
    # °F markets are out of scope: a +2 bucket there is ~1.1 °C and no city clears
    # the tail threshold. Detect on the bucket label, never on the description —
    # descriptions mention "toggle between Fahrenheit and Celsius" on every market.
    if any("°F" in (m.get("groupItemTitle") or "") for m in ms):
        return None

    def num(x):
        try:
            v = float(x)
            return 0.0 if v != v else v
        except (TypeError, ValueError):
            return 0.0

    mids = [(num(m.get("bestBid")) + num(m.get("bestAsk"))) / 2 for m in ms]
    tot = sum(mids)
    if tot <= 0:
        return None
    share = [x / tot for x in mids]
    mi = max(range(len(share)), key=lambda i: share[i])
    ti = mi + 2
    if ti >= len(ms):
        return None
    tgt = ms[ti]
    return {
        "mode": bucket_num(ms[mi].get("groupItemTitle", "")),
        "mode_share": round(share[mi], 4),
        "target_title": tgt.get("groupItemTitle", ""),
        "target": bucket_num(tgt.get("groupItemTitle", "")),
        "bid": round(num(tgt.get("bestBid")), 4),
        "ask": round(num(tgt.get("bestAsk")), 4),
        "depth": int(num(tgt.get("liquidityNum"))),
        "open_top": ti == len(ms) - 1,
        "ladder": [{"b": ms[i].get("groupItemTitle", ""), "s": round(share[i], 4)}
                   for i in range(len(ms))],
    }


def read_forecast(lat, lon, d):
    j = get(OM.format(lat=lat, lon=lon, d=d.isoformat()), pause=0.2)
    if not j:
        return None
    h = j.get("hourly") or {}
    hours = [int(t[11:13]) for t in h.get("time", [])]
    idx = [i for i, hh in enumerate(hours) if WINDOW[0] <= hh <= WINDOW[1]]
    if not idx:
        return None
    temps = h.get("temperature_2m") or []
    rain = h.get("precipitation") or []
    cloud = h.get("cloud_cover") or []
    return {
        "fcst_max": round(max(temps[i] for i in idx), 1),
        "rain_mm": round(sum((rain[i] or 0) for i in idx), 1),
        "cloud_pct": round(sum((cloud[i] or 0) for i in idx) / len(idx)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--for-date", default=None)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()

    target = date.fromisoformat(a.for_date) if a.for_date else \
             (datetime.now(timezone.utc).date() + timedelta(days=1))

    inputs_path = os.path.join(a.repo, "data", "latest.json")
    if not os.path.exists(inputs_path):
        sys.exit("no data/latest.json — run export_board_inputs.py first")
    inputs = json.load(open(inputs_path))
    stations, tails = inputs["stations"], inputs["tails"]

    excl_path = os.path.join(a.repo, "exclusions.json")
    excl = {}
    if os.path.exists(excl_path):
        for e in json.load(open(excl_path)).get("cities", []):
            until = e.get("review_by")
            if until and date.fromisoformat(until) < date.today():
                continue                     # expired exclusions lapse by default
            excl[e["city"]] = e

    rows = []
    for city in sorted(set(stations) & set(tails)):
        lad = read_ladder(city, target)
        if not lad or lad["mode"] is None or lad["target"] is None:
            continue
        st, tl = stations[city], tails[city]

        fc = read_forecast(st["lat"], st["lon"], target)
        gap = debiased = None
        if fc:
            # Apply the per-station offset. The sign is declared in the export, never
            # guessed — get it backwards and every gap on the board flips.
            off = st["debias_c"] if st["debias_sign"] == "actual_minus_forecast" else -st["debias_c"]
            debiased = round(fc["fcst_max"] + off, 1)
            gap = round(lad["mode"] - debiased, 1)

        risk = tl["p_ge2"] if lad["open_top"] else tl["p_eq2"]
        lo, hi = wilson(risk, tl["n"])
        b = lad["bid"]
        if b > 0 and risk > 0:
            fee = FEE * min(b, 1 - b)
            cost, profit = (1 - b) + fee, b - fee
            be = profit / (profit + cost)
            mult = be / risk
            ev = ((1 - risk) * profit - risk * cost) / cost
        else:
            be = mult = ev = 0.0

        pen, why = 0.0, []
        if tl["kstar"] > 2:
            pen += PEN_KSTAR; why.append(f"k*={tl['kstar']} -{PEN_KSTAR}")
        if lad["mode_share"] < MODE_FLOOR:
            p = min(PEN_MODE_CAP, (MODE_FLOOR - lad["mode_share"]) * 100)
            pen += p; why.append(f"mode {lad['mode_share']*100:.1f}% -{p:.0f}")
        if gap is not None and abs(gap) >= GAP_FLOOR:
            p = min(PEN_GAP_CAP, 15 + 15 * (abs(gap) - GAP_FLOOR))
            pen += p; why.append(f"gap {gap:+.1f} -{p:.0f}")
        if mult > CEIL_MULT:
            pen += PEN_CEIL; why.append(f"mult>{CEIL_MULT}x -{PEN_CEIL}")
        if tl["n"] < MIN_N:
            pen += PEN_SMALL_N; why.append(f"n={tl['n']} -{PEN_SMALL_N}")

        bad = []
        if b <= 0:                 bad.append("no bid")
        if lad["depth"] < MIN_DEPTH: bad.append("depth")
        if lad["open_top"]:        bad.append("open top")
        if mult <= 1.0:            bad.append("price below tail")
        if gap is None:            bad.append("no model gap")
        if city in excl:           bad.append(f"excluded: {excl[city]['reason']}")

        rows.append({
            "city": city, "station": st["icao"],
            "mode": lad["mode"], "target": lad["target"], "target_title": lad["target_title"],
            "mode_share": lad["mode_share"], "bid": b, "ask": lad["ask"],
            "depth": lad["depth"], "open_top": lad["open_top"], "ladder": lad["ladder"],
            "tail": round(risk, 4), "lo": round(lo, 4), "hi": round(hi, 4),
            "n": tl["n"], "kstar": tl["kstar"], "sd": tl.get("sd"),
            "break_even": round(be, 4), "mult": round(mult, 3), "ev": round(ev, 4),
            "fcst_max_raw": fc["fcst_max"] if fc else None,
            "fcst_max_debiased": debiased,
            "debias_c": st["debias_c"], "debias_sign": st["debias_sign"],
            "gap": gap, "rain_mm": fc["rain_mm"] if fc else None,
            "cloud_pct": fc["cloud_pct"] if fc else None,
            "_pen": pen, "_why": why, "_bad": bad,
        })

    if not rows:
        sys.exit("no ladders captured — check the Gamma feed before trusting this")

    pops = [1 - r["hi"] for r in rows]
    mults = [r["mult"] for r in rows]
    for r in rows:
        r["pop_conservative"] = round(1 - r["hi"], 4)
        r["S1"] = round(pct_rank(pops, 1 - r["hi"]), 1)
        r["S2"] = round(pct_rank(mults, r["mult"]), 1)
        r["pen"] = round(r.pop("_pen"), 1)
        r["penalties"] = r.pop("_why")
        r["score"] = round(W_POP * r["S1"] + W_PRICE * r["S2"] - r["pen"], 1)
        r["tradable"] = not r["_bad"]
        r["reason"] = "/".join(r.pop("_bad"))

    rows.sort(key=lambda r: -r["score"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["stamp"] = ("selected" if (r["tradable"] and i <= a.top)
                      else ("eligible" if r["tradable"] else "control"))

    doc = {
        "date": target.isoformat(),
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "builder": "build_predictions/1.0.0",
        "snapshot": inputs["tail_snapshot_id"],
        "debias_applied": True,
        "weights": {"pop": W_POP, "price": W_PRICE},
        "top": a.top,
        "field": len(rows),
        "selected": sum(1 for r in rows if r["stamp"] == "selected"),
        "eligible_unranked": sum(1 for r in rows if r["stamp"] == "eligible"),
        "exclusions": sorted(excl),
        "rows": rows,
    }
    out = os.path.join(a.repo, "predictions", f"{target.isoformat()}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(doc, open(out, "w"), indent=1, sort_keys=True)
    print(f"{target}: field {len(rows)}, selected {doc['selected']}, "
          f"eligible-but-unranked {doc['eligible_unranked']}, snapshot {doc['snapshot']}")
    for r in rows[:a.top]:
        print(f"  {r['rank']:>2} {r['city']:<15}{r['stamp']:<9}{r['mult']:>6.2f}x  "
              f"tail {r['tail']*100:>4.1f}%  gap {('%+.1f' % r['gap']) if r['gap'] is not None else '  --'}"
              f"   {r['reason']}")

    if a.push:
        def git(*x): subprocess.run(["git", "-C", a.repo, *x], check=True)
        git("add", "predictions")
        if subprocess.run(["git", "-C", a.repo, "diff", "--cached", "--quiet"]).returncode:
            git("commit", "-m", f"board: {target.isoformat()} ({doc['selected']} selected)")
            git("push")
            print("pushed")


if __name__ == "__main__":
    main()
