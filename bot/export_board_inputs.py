#!/usr/bin/env python3
"""
export_board_inputs.py — run on the droplet, after the nightly wxfeatures pass.

Reads wx.db and writes data/YYYY-MM-DD.json + data/latest.json, then optionally
commits and pushes. Model inputs only: de-bias offsets, the bt_daily tail snapshot,
and recent settled outcomes. Never fills, sizes or account state.

    python3 bot/export_board_inputs.py --db /opt/wx/wx.db --repo /opt/plus-two-board --push

The two things that matter most:

  * DEBIAS_SIGN must describe what the number actually is. Get it backwards and every
    model gap on the board flips sign. There is deliberately no default.
  * TAIL_SNAPSHOT_ID must change whenever the de-bias run changes, because a bad
    de-bias changes every gate outcome with no code change at all.

The SQL below is written against the schema as documented; if your column names differ,
fix the queries here rather than reshaping the output — the board and the self-check
both read the JSON contract, not the database.
"""
import argparse, json, math, os, sqlite3, subprocess, sys
from datetime import datetime, timezone, date, timedelta

CODE_VERSION   = "export_board_inputs/1.0.0"
DEBIAS_SIGN    = "actual_minus_forecast"   # <-- VERIFY THIS AGAINST YOUR OWN PIPELINE
DEBIAS_METHOD  = "trailing60_median"
SEASON_WINDOW  = 45     # +/- days around the target day-of-year
DEBIAS_WINDOW  = 60     # trailing days for the median offset
MIN_N          = 30


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def table_exists(cx, name):
    return cx.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def load_stations(cx):
    """city slug -> station metadata + de-bias offset."""
    out = {}
    rows = cx.execute("""
        SELECT city, icao, lat, lon
          FROM stations
    """).fetchall()
    for city, icao, lat, lon in rows:
        out[city] = {
            "icao": (icao or "").upper(),
            "lat": round(float(lat), 4),
            "lon": round(float(lon), 4),
            "debias_sign": DEBIAS_SIGN,
            "debias_method": DEBIAS_METHOD,
        }

    # Trailing-window median of (actual - forecast), per station, out of sample.
    cutoff = (date.today() - timedelta(days=DEBIAS_WINDOW)).isoformat()
    resid = cx.execute("""
        SELECT city, actual_res - fcst_raw AS e
          FROM bt_daily
         WHERE day >= ?
           AND actual_res IS NOT NULL
           AND fcst_raw   IS NOT NULL
    """, (cutoff,)).fetchall()

    by = {}
    for city, e in resid:
        by.setdefault(city, []).append(float(e))
    for city, es in by.items():
        if city not in out or len(es) < 5:
            continue
        es.sort()
        m = len(es)
        med = es[m // 2] if m % 2 else 0.5 * (es[m // 2 - 1] + es[m // 2])
        out[city]["debias_c"] = round(med, 2)
        out[city]["debias_n"] = m
        out[city]["debias_asof"] = date.today().isoformat()

    # A station with no offset is worse than useless — it would be silently treated as
    # zero downstream. Drop it and let the board show the city as un-de-biased.
    missing = [c for c, v in out.items() if "debias_c" not in v]
    for c in missing:
        del out[c]
    if missing:
        print(f"  warning: no de-bias offset for {len(missing)} stations: "
              f"{', '.join(sorted(missing)[:8])}", file=sys.stderr)
    return out


def load_tails(cx, target_doy):
    """Measured +2 tails from bt_daily, seasonal window, de-biased forecast."""
    rows = cx.execute("""
        SELECT city,
               actual_res,
               fcst_raw,
               CAST(strftime('%j', day) AS INTEGER) AS doy
          FROM bt_daily
         WHERE actual_res IS NOT NULL
           AND fcst_raw   IS NOT NULL
    """).fetchall()

    acc = {}
    for city, actual, fcst, doy in rows:
        if doy is None:
            continue
        d = abs(doy - target_doy)
        d = min(d, 365 - d)                 # wrap the year
        if d > SEASON_WINDOW:
            continue
        acc.setdefault(city, []).append((float(actual), float(fcst)))

    tails = {}
    for city, pairs in acc.items():
        n = len(pairs)
        if n < MIN_N:
            continue
        # offset in whole buckets: the market's buckets are whole degrees C
        devs = [round(a) - round(f) for a, f in pairs]
        eq2 = sum(1 for d in devs if d == 2)
        ge2 = sum(1 for d in devs if d >= 2)
        lo, hi = wilson(eq2, n)
        # k* = smallest offset whose exceedance falls under the 8.5% break-even
        kstar = None
        for k in range(1, 8):
            if sum(1 for d in devs if d >= k) / n < 0.085:
                kstar = k
                break
        mean = sum(d for d in devs) / n
        sd = math.sqrt(sum((d - mean) ** 2 for d in devs) / max(n - 1, 1))
        tails[city] = {
            "n": n,
            "sd": round(sd, 2),
            "p_eq2": round(eq2 / n, 4),
            "p_ge2": round(ge2 / n, 4),
            "kstar": kstar if kstar is not None else 8,
            "lo": round(lo, 4),
            "hi": round(hi, 4),
        }
    return tails


def load_settled(cx, days=14):
    if not table_exists(cx, "outcomes"):
        return {}
    since = (date.today() - timedelta(days=days)).isoformat()
    out = {}
    for day, city, actual in cx.execute(
        "SELECT day, city, actual_res FROM outcomes WHERE day >= ? AND actual_res IS NOT NULL",
        (since,),
    ):
        out.setdefault(day, {})[city] = int(round(float(actual)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/opt/wx/wx.db")
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--for-date", default=None,
                    help="Trading day the export is for (default: tomorrow UTC).")
    ap.add_argument("--snapshot-id", default=None)
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()

    target = date.fromisoformat(a.for_date) if a.for_date else \
             (datetime.now(timezone.utc).date() + timedelta(days=1))
    snapshot = a.snapshot_id or f"bt-{date.today().isoformat()}-w{SEASON_WINDOW}-med{DEBIAS_WINDOW}"

    cx = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    stations = load_stations(cx)
    tails    = load_tails(cx, int(target.strftime("%j")))
    settled  = load_settled(cx)
    nrows    = cx.execute("SELECT COUNT(*) FROM bt_daily").fetchone()[0]
    lo_day, hi_day = cx.execute("SELECT MIN(day), MAX(day) FROM bt_daily").fetchone()
    cx.close()

    doc = {
        "schema": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_version": CODE_VERSION,
        "tail_snapshot_id": snapshot,
        "backtest": {
            "rows": nrows,
            "stations": len(stations),
            "date_from": lo_day,
            "date_to": hi_day,
            "window_days": SEASON_WINDOW,
            "debias_window_days": DEBIAS_WINDOW,
            "lead_hours": 24,
        },
        "stations": stations,
        "tails": tails,
    }
    if settled:
        doc["settled"] = settled

    if not stations or not tails:
        sys.exit("refusing to write: stations or tails came back empty — check the SQL")

    ddir = os.path.join(a.repo, "data")
    os.makedirs(ddir, exist_ok=True)
    dated = os.path.join(ddir, f"{target.isoformat()}.json")
    for path in (dated, os.path.join(ddir, "latest.json")):
        with open(path, "w") as f:
            json.dump(doc, f, indent=1, sort_keys=True)
            f.write("\n")

    print(f"wrote {dated}: {len(stations)} stations, {len(tails)} tails, "
          f"snapshot {snapshot}")

    if a.push:
        def git(*args):
            subprocess.run(["git", "-C", a.repo, *args], check=True)
        git("add", "data")
        r = subprocess.run(["git", "-C", a.repo, "diff", "--cached", "--quiet"])
        if r.returncode == 0:
            print("nothing to commit")
            return
        git("commit", "-m", f"inputs: {target.isoformat()} ({snapshot})")
        git("push")
        print("pushed")


if __name__ == "__main__":
    main()
