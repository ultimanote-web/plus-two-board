#!/usr/bin/env python3
"""
export_board_inputs.py — run on the droplet, nightly, after the wxfeatures pass.

Reads wx.db and writes data/YYYY-MM-DD.json + data/latest.json, then optionally
commits and pushes. Model inputs only: station metadata, de-bias offsets, and the
measured tail snapshot. Never fills, sizes or account state.

    python3 bot/export_board_inputs.py --db /root/wxbot/wx.db --push

It READS tail_city and tail_snapshot. It does not recompute them. A second
implementation of the tail would silently drift from the one the backtest actually
used, and the whole point of the snapshot id is that a board can name the exact
numbers it scored against.

Schema it expects (confirmed against the live database 2026-09-12):
    tail_snapshot(snapshot_id, generated_at, debias_days, centre_doy, half_width,
                  min_hours, bt_max_date, n_cities, note)
    tail_city(snapshot_id, city, unit, n, p2, p2_lo, p2_hi, ge2, k_star,
              k_star_firm, sd, exact_hit, debias_median)
    bt_daily(icao, city, obs_date, unit, fcst_raw, actual_res, n_hours)

DEBIAS SIGN — established empirically on 2026-09-12 by comparing tail_city.debias_median
against median(actual_res - fcst_raw) recomputed from bt_daily: they agree in sign and
approximately in magnitude, the residual difference being the seasonal window. So
debias_median is ACTUAL MINUS FORECAST: positive means the station reads hotter than
Open-Meteo predicted, and the de-biased forecast is fcst + debias_median.
"""
import argparse, json, os, sqlite3, subprocess, sys, unicodedata
from datetime import datetime, timezone, date, timedelta

CODE_VERSION = "export_board_inputs/2.0.0"
DEBIAS_SIGN  = "actual_minus_forecast"     # see the note above — established, not assumed
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Gates in force, exported so the self-check can enforce expiry without being told.
GATES = [
    {"name": "k* = 2",            "threshold": 2,    "adopted": "2026-09-06", "provisional": False,
     "reason": "measured exceedance at +2 under the 8.5% break-even"},
    {"name": "mode share >= 35%", "threshold": 0.35, "adopted": "2026-09-09", "provisional": True,
     "expires": "2026-10-21",
     "reason": "flat ladders make '+2' meaningless; never backtested, same n=1 origin as the ceiling"},
    {"name": "depth >= $600",     "threshold": 600,  "adopted": "2026-09-06", "provisional": False,
     "reason": "below this the book cannot be worked"},
    {"name": "closed top bucket", "threshold": None, "adopted": "2026-09-06", "provisional": False,
     "reason": "an open end prices an unbounded tail as one bucket; vindicated by Karachi 2026-09-12"},
    {"name": "multiple > 1.00",   "threshold": 1.0,  "adopted": "2026-09-06", "provisional": False,
     "reason": "a price at or below the measured tail is not a trade at any rank"},
    {"name": "multiple <= 2.5x",  "threshold": 2.5,  "adopted": "2026-09-09", "provisional": True,
     "expires": "2026-10-21",
     "reason": "adopted from Munich alone, n=1; lapses by default under the ratchet rule"},
]


def slugify(city, overrides):
    if city in overrides:
        return overrides[city]
    s = unicodedata.normalize("NFKD", city)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().replace(" ", "-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/root/wxbot/wx.db")
    ap.add_argument("--repo", default=ROOT)
    ap.add_argument("--for-date", default=None, help="Trading day (default: tomorrow UTC)")
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()

    target = date.fromisoformat(a.for_date) if a.for_date else \
             (datetime.now(timezone.utc).date() + timedelta(days=1))

    meta = json.load(open(os.path.join(a.repo, "schema", "stations.json")))
    COORDS, OVERRIDES = meta["stations"], meta.get("slug_overrides", {})

    cx = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    cx.row_factory = sqlite3.Row

    snap = cx.execute(
        "SELECT * FROM tail_snapshot ORDER BY generated_at DESC LIMIT 1").fetchone()
    if not snap:
        sys.exit("tail_snapshot is empty — run the backtest build first")
    snap = dict(snap)
    sid = snap["snapshot_id"]

    icao_of = {r["city"]: r["icao"] for r in cx.execute(
        "SELECT DISTINCT city, icao FROM bt_daily WHERE unit='C'")}

    stations, tails, skipped = {}, {}, []
    for r in cx.execute(
            "SELECT * FROM tail_city WHERE snapshot_id=? AND unit='C' ORDER BY city", (sid,)):
        r = dict(r)
        city = r["city"]
        icao = icao_of.get(city)
        if not icao:
            skipped.append(f"{city} (no icao in bt_daily)"); continue
        if icao not in COORDS:
            skipped.append(f"{city}/{icao} (no coordinates in schema/stations.json)"); continue
        if r["debias_median"] is None:
            skipped.append(f"{city} (no debias_median)"); continue

        slug = slugify(city, OVERRIDES)
        c = COORDS[icao]
        stations[slug] = {
            "display": city,
            "icao": icao,
            "station_name": c["name"],
            "lat": c["lat"],
            "lon": c["lon"],
            "station_verified": bool(c.get("verified")),
            "debias_c": round(float(r["debias_median"]), 2),
            "debias_sign": DEBIAS_SIGN,
            "debias_n": snap["debias_days"],
            "debias_method": f"median residual, {snap['debias_days']}d, seasonal window",
            "debias_asof": snap["bt_max_date"],
        }
        tails[slug] = {
            "n": int(r["n"]),
            "sd": round(float(r["sd"]), 3) if r["sd"] is not None else None,
            "p_eq2": round(float(r["p2"]), 4),
            "p_ge2": round(float(r["ge2"]), 4),
            "kstar": int(r["k_star"]),
            "kstar_firm": (bool(r["k_star_firm"]) if r["k_star_firm"] is not None else None),
            "lo": round(float(r["p2_lo"]), 4),
            "hi": round(float(r["p2_hi"]), 4),
        }
    cx.close()

    if not stations:
        sys.exit("no usable °C stations — refusing to write an empty export")

    doc = {
        "schema": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_version": CODE_VERSION,
        "tail_snapshot_id": sid,
        "backtest": {
            "snapshot_generated_at": snap["generated_at"],
            "debias_window_days": snap["debias_days"],
            "centre_doy": snap["centre_doy"],
            "half_width_days": snap["half_width"],
            "min_hours": snap["min_hours"],
            "date_to": snap["bt_max_date"],
            "n_cities_in_snapshot": snap["n_cities"],
            "note": snap["note"],
        },
        "stations": stations,
        "tails": tails,
        "gates": GATES,
    }

    ddir = os.path.join(a.repo, "data")
    os.makedirs(ddir, exist_ok=True)
    for p in (os.path.join(ddir, f"{target.isoformat()}.json"),
              os.path.join(ddir, "latest.json")):
        with open(p, "w") as f:
            json.dump(doc, f, indent=1, sort_keys=True)
            f.write("\n")

    print(f"{target}: {len(stations)} °C stations, snapshot {sid} (to {snap['bt_max_date']})")
    unver = [s["icao"] for s in stations.values() if not s["station_verified"]]
    if unver:
        print(f"  {len(unver)} station(s) not yet verified against the market text: "
              f"{', '.join(sorted(unver))}")
    if skipped:
        print("  skipped:")
        for s in skipped:
            print(f"    - {s}")

    if a.push:
        def git(*x): subprocess.run(["git", "-C", a.repo, *x], check=True)
        git("add", "data")
        if subprocess.run(["git", "-C", a.repo, "diff", "--cached", "--quiet"]).returncode:
            git("commit", "-m", f"inputs: {target.isoformat()} ({sid})")
            git("push")
            print("  pushed")
        else:
            print("  nothing to commit")


if __name__ == "__main__":
    main()
