#!/usr/bin/env python3
"""
fetch_settlements.py — pull resolved outcomes for a trading day from Polymarket Gamma.

Runs on a GitHub runner, which (unlike the board's own environment) can reach
gamma-api.polymarket.com directly. Writes settled/YYYY-MM-DD.json and appends new
city-days to log/settlements.csv.

    python3 selfcheck/fetch_settlements.py --date 2026-09-12

Idempotent: city-days already in the log are not appended again, and the log is
append-only by design. Code, gates and tails are opinions and can be reverted; the
record of what actually resolved is evidence.
"""
import argparse, csv, json, os, sys, time, urllib.request
from datetime import date, datetime, timezone

GAMMA = "https://gamma-api.polymarket.com/events?slug=highest-temperature-in-{city}-on-{month}-{day}-2026"
MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Polymarket's edge 403s urllib's default agent. See build_predictions.py.
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")


def get(url, tries=3):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if i == tries - 1:
                print(f"  ! {url}: {e}", file=sys.stderr)
                return None
            time.sleep(2 * (i + 1))


def bucket_number(title):
    """'33°C' -> 33 ; '36°C or higher' -> 36 ; '27°C or below' -> 27"""
    digits = ""
    for ch in title:
        if ch.isdigit() or (ch == "-" and not digits):
            digits += ch
        elif digits:
            break
    return int(digits) if digits else None


def resolved_bucket(event):
    """The winning bucket, or None if the event has not resolved."""
    winners = []
    for m in event.get("markets", []):
        try:
            p = json.loads(m.get("outcomePrices") or "[]")
        except Exception:
            continue
        if p and float(p[0]) > 0.99:
            winners.append(m.get("groupItemTitle", ""))
    if len(winners) != 1:
        return None, None
    t = winners[0]
    return bucket_number(t), t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: yesterday UTC)")
    ap.add_argument("--cities", default=None, help="comma-separated slugs; default: from predictions/")
    a = ap.parse_args()

    d = date.fromisoformat(a.date) if a.date else \
        date.fromordinal(datetime.now(timezone.utc).date().toordinal() - 1)

    pred_path = os.path.join(ROOT, "predictions", f"{d.isoformat()}.json")
    if a.cities:
        cities = [c.strip() for c in a.cities.split(",") if c.strip()]
    elif os.path.exists(pred_path):
        cities = [r["city"] for r in json.load(open(pred_path))["rows"]]
    else:
        sys.exit(f"no predictions/{d.isoformat()}.json and no --cities; nothing to check")

    out, unresolved = {}, []
    for c in cities:
        ev = get(GAMMA.format(city=c, month=MONTHS[d.month - 1], day=d.day))
        if not ev:
            unresolved.append(c); continue
        n, title = resolved_bucket(ev[0])
        if n is None:
            unresolved.append(c)
        else:
            out[c] = {"actual": n, "bucket": title,
                      "open_ended": ("higher" in title or "above" in title or "below" in title)}
        time.sleep(0.3)

    os.makedirs(os.path.join(ROOT, "settled"), exist_ok=True)
    sp = os.path.join(ROOT, "settled", f"{d.isoformat()}.json")
    json.dump({"date": d.isoformat(),
               "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "resolved": out, "unresolved": unresolved},
              open(sp, "w"), indent=1, sort_keys=True)
    print(f"{d}: resolved {len(out)}, still open {len(unresolved)}"
          + (f" ({', '.join(unresolved)})" if unresolved else ""))

    # append to the log
    preds = {}
    if os.path.exists(pred_path):
        preds = {r["city"]: r for r in json.load(open(pred_path))["rows"]}

    lp = os.path.join(ROOT, "log", "settlements.csv")
    os.makedirs(os.path.dirname(lp), exist_ok=True)
    cols = ["date", "city", "stamp", "rank", "mode", "target", "actual", "dev", "hit",
            "tail", "lo", "hi", "n", "kstar", "mode_share", "bid", "mult", "gap",
            "rain_mm", "cloud_pct", "snapshot"]
    seen = set()
    if os.path.exists(lp):
        with open(lp) as f:
            for row in csv.DictReader(f):
                seen.add((row["date"], row["city"]))
    new = 0
    with open(lp, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if not seen:
            w.writeheader()
        for c, o in sorted(out.items()):
            if (d.isoformat(), c) in seen:
                continue
            p = preds.get(c, {})
            mode = p.get("mode")
            dev = (o["actual"] - mode) if mode is not None else None
            w.writerow({
                "date": d.isoformat(), "city": c,
                "stamp": p.get("stamp", ""), "rank": p.get("rank", ""),
                "mode": mode, "target": p.get("target", ""), "actual": o["actual"],
                "dev": dev, "hit": (1 if (dev is not None and dev >= 2) else 0),
                "tail": p.get("tail", ""), "lo": p.get("lo", ""), "hi": p.get("hi", ""),
                "n": p.get("n", ""), "kstar": p.get("kstar", ""),
                "mode_share": p.get("mode_share", ""), "bid": p.get("bid", ""),
                "mult": p.get("mult", ""), "gap": p.get("gap", ""),
                "rain_mm": p.get("rain_mm", ""), "cloud_pct": p.get("cloud_pct", ""),
                "snapshot": p.get("snapshot", ""),
            })
            new += 1
    print(f"appended {new} rows to log/settlements.csv")


if __name__ == "__main__":
    main()
