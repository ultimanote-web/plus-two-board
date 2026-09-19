#!/usr/bin/env python3
"""
capture_ladders.py — record the full price ladder for every city, once per trading day.

Why this exists
---------------
The settlement log answers "what happened". It does not answer "what was it priced
at", and the two open questions after 2026-09-19 both need prices:

  1. The distribution is left-skewed — P(dev <= -2) = 7.0% against P(dev >= +2) = 3.7%
     over 242 settled city-days. Does the market price that asymmetry, or does it quote
     the two sides alike? If alike, the cold side is systematically dear.
  2. Any forward test of the tails needs the implied probability at decision time, not
     a reconstruction from memory.

predictions/ already stores a price, but only for the +2 bucket of rows that survived
the gates. That is the selected subset — the exact place where a price sample is least
trustworthy. This captures the whole ladder for the whole field, including rows nothing
would ever trade, so the price series is not conditioned on the selector.

    python3 selfcheck/capture_ladders.py                  # tomorrow UTC
    python3 selfcheck/capture_ladders.py --date 2026-09-20

Writes ladders/YYYY-MM-DD.json (raw, every bucket) and appends one summary row per
city to log/ladders.csv. Idempotent on (date, city): re-running never double-appends,
and the raw file is overwritten only by a later capture of the same day.

Raw first, derived second, on purpose. Every number in the CSV is recomputable from
the JSON, so a mistake in the summary costs a rerun of the analysis rather than a
lost day of prices.
"""
import argparse, csv, json, os, sys, time, urllib.request
from datetime import date, datetime, timedelta, timezone

GAMMA = "https://gamma-api.polymarket.com/events?slug=highest-temperature-in-{city}-on-{month}-{day}-2026"
MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Polymarket's edge 403s urllib's default agent. See build_predictions.py — this bit
# them silently in fetch_settlements.py for several days before anyone noticed.
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")

COLS = ["date", "city", "captured_utc", "n_buckets", "book_sum",
        "mode", "mode_title", "mode_p", "top_open", "bot_open",
        "p_up2", "p_dn2", "cum_up2", "cum_dn2",
        "bid_up2", "ask_up2", "depth_up2",
        "bid_dn2", "ask_dn2", "depth_dn2"]


def get(url, tries=3, pause=0.3):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                time.sleep(pause)
                return json.loads(r.read().decode())
        except Exception as e:
            if i == tries - 1:
                print(f"  ! {url}: {e}", file=sys.stderr)
                return None
            time.sleep(2 * (i + 1))


def num(x):
    try:
        v = float(x)
        return 0.0 if v != v else v
    except (TypeError, ValueError):
        return 0.0


def bucket_num(title):
    """'33°C' -> 33 ; '36°C or higher' -> 36 ; '-3°C or below' -> -3"""
    digits = ""
    for ch in title:
        if ch.isdigit() or (ch == "-" and not digits):
            digits += ch
        elif digits:
            break
    return int(digits) if digits else None


def open_ended(title):
    t = (title or "").lower()
    return ("higher" in t) or ("above" in t) or ("below" in t) or ("lower" in t)


def capture(city, d):
    ev = get(GAMMA.format(city=city, month=MONTHS[d.month - 1], day=d.day))
    if not ev:
        return None
    ms = ev[0].get("markets", [])
    if len(ms) < 5:
        return None
    # °F markets are out of scope — a +2 bucket there is ~1.1 °C. Detect on the bucket
    # label, never the description: every description mentions the F/C toggle.
    if any("°F" in (m.get("groupItemTitle") or "") for m in ms):
        return None

    rungs = []
    for m in ms:
        t = m.get("groupItemTitle") or ""
        rungs.append({
            "title": t,
            "deg": bucket_num(t),
            "open": open_ended(t),
            "bid": round(num(m.get("bestBid")), 4),
            "ask": round(num(m.get("bestAsk")), 4),
            "liq": round(num(m.get("liquidityNum")), 2),
            "vol": round(num(m.get("volumeNum")), 2),
        })
    for r in rungs:
        r["mid"] = round((r["bid"] + r["ask"]) / 2, 4)
    return rungs


def summarize(d, city, rungs, captured):
    tot = sum(r["mid"] for r in rungs)
    if tot <= 0:
        return None
    for r in rungs:
        r["p"] = r["mid"] / tot

    mi = max(range(len(rungs)), key=lambda i: rungs[i]["p"])
    mode_deg = rungs[mi]["deg"]
    if mode_deg is None:
        return None

    def at(offset):
        """The rung exactly `offset` degrees from the mode, by label, not by index.

        Index arithmetic is wrong here: ladders are not always contiguous and the
        open-ended ends do not represent one degree. Matching on the degree label
        means a missing rung returns None instead of silently returning its
        neighbour, which is the kind of error that reads as a finding."""
        want = mode_deg + offset
        for r in rungs:
            if r["deg"] == want and not r["open"]:
                return r
        # the open-ended ends carry the right degree but an unbounded range; they are
        # returned so the caller can see them, flagged by r["open"]
        for r in rungs:
            if r["deg"] == want:
                return r
        return None

    up2, dn2 = at(+2), at(-2)
    cum_up2 = sum(r["p"] for r in rungs if r["deg"] is not None and r["deg"] >= mode_deg + 2)
    cum_dn2 = sum(r["p"] for r in rungs if r["deg"] is not None and r["deg"] <= mode_deg - 2)

    return {
        "date": d.isoformat(), "city": city, "captured_utc": captured,
        "n_buckets": len(rungs), "book_sum": round(tot, 4),
        "mode": mode_deg, "mode_title": rungs[mi]["title"], "mode_p": round(rungs[mi]["p"], 4),
        "top_open": int(bool(rungs[-1]["open"])), "bot_open": int(bool(rungs[0]["open"])),
        "p_up2": round(up2["p"], 4) if up2 else "",
        "p_dn2": round(dn2["p"], 4) if dn2 else "",
        "cum_up2": round(cum_up2, 4), "cum_dn2": round(cum_dn2, 4),
        "bid_up2": up2["bid"] if up2 else "", "ask_up2": up2["ask"] if up2 else "",
        "depth_up2": int(up2["liq"]) if up2 else "",
        "bid_dn2": dn2["bid"] if dn2 else "", "ask_dn2": dn2["ask"] if dn2 else "",
        "depth_dn2": int(dn2["liq"]) if dn2 else "",
    }


def city_list(repo):
    p = os.path.join(repo, "data", "latest.json")
    if os.path.exists(p):
        j = json.load(open(p))
        return sorted(set(j.get("stations", {})) & set(j.get("tails", {})))
    # fall back to whatever the settlement log has seen, so a missing export does not
    # cost a day of prices
    lp = os.path.join(repo, "log", "settlements.csv")
    if os.path.exists(lp):
        return sorted({r["city"] for r in csv.DictReader(open(lp)) if r.get("city")})
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=ROOT)
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: tomorrow UTC)")
    ap.add_argument("--cities", default=None, help="comma-separated slugs")
    a = ap.parse_args()

    d = date.fromisoformat(a.date) if a.date else \
        datetime.now(timezone.utc).date() + timedelta(days=1)
    cities = [c.strip() for c in a.cities.split(",")] if a.cities else city_list(a.repo)
    if not cities:
        sys.exit("no city list — need data/latest.json, log/settlements.csv, or --cities")

    captured = datetime.now(timezone.utc).isoformat(timespec="seconds")
    raw, rows, skipped = {}, [], []
    for c in cities:
        rungs = capture(c, d)
        if not rungs:
            skipped.append(c)
            continue
        raw[c] = rungs
        s = summarize(d, c, rungs, captured)
        if s:
            rows.append(s)
        else:
            skipped.append(c)

    os.makedirs(os.path.join(a.repo, "ladders"), exist_ok=True)
    json.dump({"date": d.isoformat(), "captured_utc": captured,
               "cities": raw, "skipped": skipped},
              open(os.path.join(a.repo, "ladders", f"{d.isoformat()}.json"), "w"),
              indent=1, sort_keys=True)

    lp = os.path.join(a.repo, "log", "ladders.csv")
    os.makedirs(os.path.dirname(lp), exist_ok=True)
    seen = set()
    if os.path.exists(lp):
        seen = {(r["date"], r["city"]) for r in csv.DictReader(open(lp))}
    new = 0
    with open(lp, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if not seen:
            w.writeheader()
        for r in sorted(rows, key=lambda x: x["city"]):
            if (r["date"], r["city"]) in seen:
                continue
            w.writerow(r)
            new += 1

    print(f"{d}: captured {len(rows)} ladders, skipped {len(skipped)}"
          + (f" ({', '.join(skipped)})" if skipped else ""))
    print(f"appended {new} rows to log/ladders.csv")

    if rows:
        mu = sum(r["cum_up2"] for r in rows) / len(rows)
        md = sum(r["cum_dn2"] for r in rows) / len(rows)
        print(f"mean implied  P(>= mode+2) {mu*100:5.2f}%   P(<= mode-2) {md*100:5.2f}%"
              f"   cold/hot {md/mu:.2f}x" if mu > 0 else "")


if __name__ == "__main__":
    main()
