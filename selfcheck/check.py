#!/usr/bin/env python3
"""
check.py — the self-check. Runs on a GitHub runner, on a schedule and on every push.

Reads log/settlements.csv, writes selfcheck/report.json and STATUS.md, and exits
non-zero when a tripwire fires. A failing run is the halt signal: the board reads
STATUS.md before building and refuses to publish a selection while it says HALTED.

What this can and cannot do, stated up front because it is the easiest thing to
misread: at a handful of trades a night, nothing here can detect a real improvement
in edge. The standard error on mean EV over a week is several times the edge being
measured. These checks catch a broken risk model, not a mediocre one, and a green
run is not evidence the strategy works.

    python3 selfcheck/check.py [--strict]
"""
import argparse, csv, json, math, os, sys
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG  = os.path.join(ROOT, "log", "settlements.csv")

P_HALT   = 0.02     # binomial P(>=k losses | tails correct) below this halts
REPEAT_DAYS = 14    # a city losing twice inside this window is a common cause
MIN_ROWS = 3


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def binom_ge(k, n, p):
    """P(X >= k) for X ~ Bin(n, p)."""
    if k <= 0:
        return 1.0
    return 1.0 - sum(math.comb(n, i) * p**i * (1 - p)**(n - i) for i in range(k))


def f(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load():
    if not os.path.exists(LOG):
        sys.exit(f"no {LOG} — run fetch_settlements.py first")
    rows = []
    with open(LOG) as fh:
        for r in csv.DictReader(fh):
            r["_tail"] = f(r.get("tail"))
            r["_hit"]  = r.get("hit") == "1"
            r["_dev"]  = f(r.get("dev"))
            st = (r.get("stamp") or "").lower()
            r["_traded"]   = st == "selected"      # in the ten AND tradable
            r["_eligible"] = st in ("selected", "eligible")
            rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="also fail on warnings, not only halts")
    a = ap.parse_args()

    rows = load()
    findings, halts, warns = [], [], []

    # ---- 1. selected rows: the number that decides whether to trade ----------
    sel = [r for r in rows if r["_traded"] and r["_tail"] is not None]
    sel_block = None
    if len(sel) >= MIN_ROWS:
        n = len(sel)
        k = sum(1 for r in sel if r["_hit"])
        exp = sum(r["_tail"] for r in sel)
        p = exp / n
        pv = binom_ge(k, n, p)
        lo, hi = wilson(k, n)
        sel_block = {"n": n, "losses": k, "expected": round(exp, 2),
                     "rate": round(k / n, 4), "ci": [round(lo, 4), round(hi, 4)],
                     "mean_tail": round(p, 4), "p_value": round(pv, 5)}
        if pv < P_HALT:
            halts.append(
                f"selected rows: {k} of {n} settled at +2 against {exp:.2f} expected — "
                f"P(>={k} | tails correct) = {pv*100:.2f}%, below the {P_HALT*100:.0f}% halt threshold")
        elif k >= 3:
            warns.append(f"selected rows: {k} losses in {n} — note it and look for a common cause")

    # ---- 2. field calibration: is the risk model broadly wrong? --------------
    fld = [r for r in rows if r["_tail"] is not None]
    fld_block = None
    if len(fld) >= 20:
        n = len(fld)
        k = sum(1 for r in fld if r["_hit"])
        exp = sum(r["_tail"] for r in fld)
        lo, hi = wilson(k, n)
        fld_block = {"n": n, "hits": k, "expected": round(exp, 2),
                     "rate": round(k / n, 4), "ci": [round(lo, 4), round(hi, 4)],
                     "mean_tail": round(exp / n, 4),
                     "t": round((k - exp) / math.sqrt(max(exp, 1e-9)), 2)}
        if exp / n > hi:
            warns.append(f"field: predicted {exp/n*100:.1f}% sits above the realized "
                         f"interval [{lo*100:.1f}-{hi*100:.1f}] — tails may be too conservative")
        if exp / n < lo:
            halts.append(f"field: predicted {exp/n*100:.1f}% sits below the realized "
                         f"interval [{lo*100:.1f}-{hi*100:.1f}] — the tails understate the risk")

    # ---- 3. per-city repeats: a common cause hiding inside an average -------
    by_city = defaultdict(list)
    for r in rows:
        if r["_hit"]:
            try:
                by_city[r["city"]].append(date.fromisoformat(r["date"]))
            except ValueError:
                pass
    repeats = []
    for city, ds in by_city.items():
        ds.sort()
        for i in range(1, len(ds)):
            if (ds[i] - ds[i - 1]).days <= REPEAT_DAYS:
                repeats.append({"city": city, "dates": [d.isoformat() for d in ds]})
                halts.append(f"{city}: settled at +2 twice within {REPEAT_DAYS} days "
                             f"({ds[i-1]} and {ds[i]}) — treat as station-specific until explained")
                break

    # ---- 4. does the tail actually order the outcomes? ----------------------
    terciles = None
    scored = sorted([r for r in fld], key=lambda r: r["_tail"])
    if len(scored) >= 30:
        t = len(scored) // 3
        terciles = []
        for lbl, grp in (("low", scored[:t]), ("mid", scored[t:2 * t]), ("high", scored[2 * t:])):
            terciles.append({"band": lbl, "n": len(grp),
                             "range": [grp[0]["_tail"], grp[-1]["_tail"]],
                             "hits": sum(1 for r in grp if r["_hit"]),
                             "expected": round(sum(r["_tail"] for r in grp), 2)})
        lo_b, hi_b = terciles[0], terciles[-1]
        if lo_b["hits"] > hi_b["hits"] and lo_b["n"] >= 15:
            warns.append("ordering: the low-tail band produced more +2 settlements than the "
                         "high-tail band — the score's primary parameter has not demonstrated "
                         "discrimination; do not tighten anything on it yet")

    # ---- 5. board size, the ratchet's canary -------------------------------
    per_day = defaultdict(int)
    for r in rows:
        if r["_traded"]:
            per_day[r["date"]] += 1
    days = sorted(per_day)
    size = {"days": len(days), "mean_picks": round(sum(per_day.values()) / len(days), 2)} if days else None
    if size and size["mean_picks"] > 0:
        yrs = 0.7 * (10 / size["mean_picks"])
        size["validation_horizon_years"] = round(yrs, 1)
        if size["mean_picks"] < 2:
            warns.append(f"board size: {size['mean_picks']} picks/day implies a "
                         f"~{yrs:.1f} year validation horizon — the strategy is becoming untestable")

    # ---- 6. is the pipeline alive? -----------------------------------------
    # A dead cron looks exactly like a healthy one from the outside: the files are
    # still there, the numbers still parse, and the board quietly runs on last week's
    # de-bias. Staleness has to be checked explicitly or it is never noticed.
    gates_block = []
    pipeline = {}
    latest = os.path.join(ROOT, "data", "latest.json")
    if os.path.exists(latest):
        try:
            doc = json.load(open(latest))
            gen = datetime.fromisoformat(doc["generated_utc"])
            if gen.tzinfo is None:
                gen = gen.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - gen).total_seconds() / 3600
            pipeline = {"inputs_age_hours": round(age_h, 1),
                        "snapshot": doc.get("tail_snapshot_id"),
                        "stations": len(doc.get("stations") or {}),
                        "tails": len(doc.get("tails") or {})}
            if age_h > 72:
                halts.append(f"data/latest.json is {age_h/24:.1f} days old — the droplet export "
                             f"has stopped and the board would be scoring on a stale snapshot")
            elif age_h > 36:
                warns.append(f"data/latest.json is {age_h:.0f} h old — the droplet export "
                             f"looks to have missed a run")
            missing_off = [c for c, s in (doc.get("stations") or {}).items()
                           if "debias_c" not in s]
            if missing_off:
                warns.append(f"{len(missing_off)} station(s) carry no de-bias offset: "
                             f"{', '.join(sorted(missing_off)[:6])}")
            for g in (doc.get("gates") or []):
                gates_block.append(g)
                if g.get("provisional") and g.get("expires"):
                    if date.fromisoformat(g["expires"]) < date.today():
                        warns.append(f"gate '{g['name']}' was provisional and expired "
                                     f"{g['expires']} — retire it or backtest it")
        except Exception as e:
            warns.append(f"could not read data/latest.json: {e}")
    else:
        warns.append("no data/latest.json — the bot export has not run; the board is "
                     "running without per-station de-bias offsets")

    # ---- 6b. did a board actually get built and logged? --------------------
    y = date.today() - timedelta(days=1)
    if not os.path.exists(os.path.join(ROOT, "predictions", f"{y.isoformat()}.json")):
        warns.append(f"no predictions/{y.isoformat()}.json — either no board was built "
                     f"for that day, or it was built and never logged. An unlogged board "
                     f"cannot be checked.")

    # ---- 6c. manual exclusions, and whether they have gone stale -----------
    exclusions = []
    ep = os.path.join(ROOT, "exclusions.json")
    if os.path.exists(ep):
        try:
            for e in json.load(open(ep)).get("cities", []):
                rb = e.get("review_by")
                expired = bool(rb) and date.fromisoformat(rb) < date.today()
                exclusions.append({**e, "expired": expired})
                if expired:
                    warns.append(f"exclusion on {e['city']} passed its review date {rb} — "
                                 f"clear it or renew it with a reason; it is currently lapsed")
                elif not rb:
                    warns.append(f"exclusion on {e['city']} has no review_by date — an "
                                 f"exclusion that never expires is a ratchet")
        except Exception as e:
            warns.append(f"could not read exclusions.json: {e}")

    # ---- 7. data integrity -------------------------------------------------
    bad = [r for r in rows if r["_dev"] is not None and abs(r["_dev"]) > 8]
    if bad:
        warns.append(f"{len(bad)} settlement(s) more than 8 buckets from the mode — "
                     f"check the ladder and the resolution source")

    status = "HALTED" if halts else ("WARN" if warns else "OK")
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "selected": sel_block,
        "field": fld_block,
        "terciles": terciles,
        "repeats": repeats,
        "board_size": size,
        "gates": gates_block,
        "pipeline": pipeline,
        "exclusions": exclusions,
        "halts": halts,
        "warnings": warns,
    }
    os.makedirs(os.path.join(ROOT, "selfcheck"), exist_ok=True)
    json.dump(report, open(os.path.join(ROOT, "selfcheck", "report.json"), "w"),
              indent=1, sort_keys=True)

    # ---- STATUS.md ---------------------------------------------------------
    L = [f"# {status}", "",
         f"_self-check {report['generated_utc']}_", ""]
    if halts:
        L += ["## Do not trade the next board", ""] + [f"- {h}" for h in halts] + [""]
    if sel_block:
        L += ["## Selected rows", "",
              f"- {sel_block['losses']} of {sel_block['n']} settled at +2 "
              f"({sel_block['rate']*100:.0f}%), against {sel_block['expected']} expected",
              f"- P(>= {sel_block['losses']} | tails correct) = {sel_block['p_value']*100:.2f}%",
              f"- 95% CI on the realized rate: "
              f"{sel_block['ci'][0]*100:.0f}-{sel_block['ci'][1]*100:.0f}%", ""]
    if fld_block:
        L += ["## Whole field", "",
              f"- {fld_block['hits']} of {fld_block['n']} at >=+2 "
              f"({fld_block['rate']*100:.1f}%) against {fld_block['mean_tail']*100:.1f}% predicted, "
              f"t = {fld_block['t']:+.2f}", ""]
    if terciles:
        L += ["## Does the tail order the outcomes?", "",
              "| band | range | n | hits | expected |", "|---|---|---|---|---|"]
        L += [f"| {t['band']} | {t['range'][0]*100:.1f}-{t['range'][1]*100:.1f}% | "
              f"{t['n']} | {t['hits']} | {t['expected']} |" for t in terciles]
        L += [""]
    if exclusions:
        L += ["## Manual exclusions", ""]
        L += [f"- **{e['city']}** — {e.get('reason','')} "
              f"(review by {e.get('review_by','never')}"
              f"{', LAPSED' if e.get('expired') else ''})" for e in exclusions]
        L += [""]
    if pipeline:
        L += ["## Pipeline", "",
              f"- inputs {pipeline.get('inputs_age_hours','?')} h old, snapshot "
              f"`{pipeline.get('snapshot','?')}`, {pipeline.get('stations','?')} stations / "
              f"{pipeline.get('tails','?')} tails", ""]
    if warns:
        L += ["## Warnings", ""] + [f"- {w}" for w in warns] + [""]
    L += ["---", "",
          "At this sample size these checks catch a broken risk model, not a mediocre one.",
          "A green run is not evidence the strategy works."]
    open(os.path.join(ROOT, "STATUS.md"), "w").write("\n".join(L) + "\n")

    print("\n".join(L))
    if halts or (a.strict and warns):
        sys.exit(1)


if __name__ == "__main__":
    main()
