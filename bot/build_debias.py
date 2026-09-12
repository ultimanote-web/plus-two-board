#!/usr/bin/env python3
"""
build_debias.py — measure the de-bias offset against the forecast the BOARD computes.

Why this exists. wx.db already carries tail_city.debias_median, measured as
median(actual_res - bt_daily.fcst_raw). But the board does not have fcst_raw; it
computes its own forecast live from Open-Meteo as the max over local 11:00-17:00.
On 2026-09-12, check_provenance.py showed those two quantities agree at Shenzhen
(+0.05), Chongqing (+0.12), Paris (-0.09) and London (-0.24) -- and disagree badly at
Seoul (+1.66) and Tokyo (+0.73). Applying an offset calibrated against fcst_raw to a
forecast that is 1.66 C higher does not remove bias, it double-counts it.

So measure the offset against the quantity actually used:

    debias_om[station] = median( actual_res  -  Open-Meteo 11:00-17:00 max )

taken over bt_daily's own actuals, in the snapshot's seasonal window. Offset and
forecast are then the same quantity by construction and the sign cannot drift.

    python3 -u bot/build_debias.py --db /root/wxbot/wx.db

Writes data/debias_om.json. Roughly 3 archive calls per station (one per year's
window), a couple of minutes total.

It also reports the RESIDUAL SPREAD per station, which bt_daily's bucket frequency
does not expose: a station whose forecast error is wide has a tail that is understated
no matter how well centred the median is. That is the Shenzhen question.
"""
import argparse, json, os, sqlite3, statistics, sys, time, urllib.request
from datetime import date, datetime, timezone, timedelta

ARCHIVE = ("https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
           "&hourly=temperature_2m&start_date={a}&end_date={b}&timezone=auto")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOW = (11, 17)
MIN_DAYS = 25


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if i == tries - 1:
                print(f"    ! {e}", file=sys.stderr)
                return None
            time.sleep(3 * (i + 1))


def daily_window_max(j, lo, hi):
    """{'YYYY-MM-DD': max temp over [lo,hi] local}"""
    h = (j or {}).get("hourly") or {}
    ts, vs = h.get("time") or [], h.get("temperature_2m") or []
    out = {}
    for s, v in zip(ts, vs):
        if v is None or len(s) < 13:
            continue
        if lo <= int(s[11:13]) <= hi:
            d = s[:10]
            if d not in out or v > out[d]:
                out[d] = v
    return out


def season_ranges(lo_date, hi_date, centre_doy, half):
    """One (start, end) per year covering the seasonal window."""
    out = []
    for y in range(lo_date.year, hi_date.year + 1):
        c = date(y, 1, 1) + timedelta(days=centre_doy - 1)
        a, b = c - timedelta(days=half), c + timedelta(days=half)
        a, b = max(a, lo_date), min(b, hi_date)
        if a <= b:
            out.append((a, b))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/root/wxbot/wx.db")
    ap.add_argument("--repo", default=ROOT)
    ap.add_argument("--only", default=None, help="comma-separated display names, for testing")
    a = ap.parse_args()

    meta = json.load(open(os.path.join(a.repo, "schema", "stations.json")))
    COORDS, OVERRIDES = meta["stations"], meta.get("slug_overrides", {})
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from export_board_inputs import slugify

    cx = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    cx.row_factory = sqlite3.Row
    snap = dict(cx.execute(
        "SELECT * FROM tail_snapshot ORDER BY generated_at DESC LIMIT 1").fetchone())
    centre_doy, half = int(snap["centre_doy"]), int(snap["half_width"])

    cities = [r["city"] for r in cx.execute(
        "SELECT DISTINCT city FROM bt_daily WHERE unit='C' ORDER BY city")]
    if a.only:
        keep = {c.strip() for c in a.only.split(",")}
        cities = [c for c in cities if c in keep]

    print(f"window: doy {centre_doy} +/- {half} d   stations: {len(cities)}\n")
    print(f"{'city':<14}{'icao':<6}{'n':>5}{'median':>9}{'mean':>8}{'sd':>7}"
          f"{'p10':>7}{'p90':>7}{'>=+2':>7}  vs fcst_raw")
    print("-" * 88)

    out, skipped = {}, []
    for city in cities:
        rows = cx.execute(
            "SELECT obs_date, icao, actual_res FROM bt_daily "
            "WHERE city=? AND unit='C' AND actual_res IS NOT NULL ORDER BY obs_date",
            (city,)).fetchall()
        if not rows:
            skipped.append(f"{city}: no actuals"); continue
        icao = rows[0]["icao"]
        if icao not in COORDS:
            skipped.append(f"{city}/{icao}: no coordinates"); continue
        lat, lon = COORDS[icao]["lat"], COORDS[icao]["lon"]

        actual = {r["obs_date"]: float(r["actual_res"]) for r in rows}
        lo_d = date.fromisoformat(min(actual)); hi_d = date.fromisoformat(max(actual))

        fc = {}
        for s, e in season_ranges(lo_d, hi_d, centre_doy, half):
            j = get(ARCHIVE.format(lat=lat, lon=lon, a=s.isoformat(), b=e.isoformat()))
            fc.update(daily_window_max(j, *WINDOW))
            time.sleep(0.4)

        res = [actual[d] - fc[d] for d in sorted(set(actual) & set(fc))]
        if len(res) < MIN_DAYS:
            skipped.append(f"{city}: only {len(res)} overlapping days"); continue

        res.sort()
        n = len(res)
        med = statistics.median(res)
        mean = statistics.mean(res)
        sd = statistics.pstdev(res)
        p10 = res[int(0.10 * n)]
        p90 = res[min(int(0.90 * n), n - 1)]
        # share of days the actual came in 2 C or more ABOVE the de-biased forecast --
        # a direct, forecast-native check on whether the bucket tail is understated
        ge2 = sum(1 for x in res if x - med >= 2.0) / n

        old = cx.execute(
            "SELECT debias_median FROM tail_city WHERE city=? AND unit='C' "
            "ORDER BY snapshot_id DESC LIMIT 1", (city,)).fetchone()
        old = round(float(old[0]), 2) if old and old[0] is not None else None

        slug = slugify(city, OVERRIDES)
        out[slug] = {
            "display": city, "icao": icao, "n_days": n,
            "debias_c": round(med, 2), "mean": round(mean, 2), "sd": round(sd, 2),
            "p10": round(p10, 2), "p90": round(p90, 2),
            "resid_ge2_share": round(ge2, 4),
            "debias_sign": "actual_minus_forecast",
            "debias_method": f"median(actual - Open-Meteo {WINDOW[0]}:00-{WINDOW[1]}:00 max), "
                             f"seasonal window doy {centre_doy} +/- {half}",
            "wxdb_debias_median": old,
            "delta_vs_wxdb": (round(med - old, 2) if old is not None else None),
        }
        d = out[slug]
        print(f"{city:<14}{icao:<6}{n:>5}{med:>+9.2f}{mean:>+8.2f}{sd:>7.2f}"
              f"{p10:>+7.2f}{p90:>+7.2f}{ge2*100:>6.1f}%  "
              f"{'' if old is None else f'{old:+.2f} (delta {med-old:+.2f})'}")

    cx.close()
    if not out:
        sys.exit("nothing measured — refusing to write an empty file")

    doc = {
        "schema": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "builder": "build_debias/1.0.0",
        "forecast_definition": f"Open-Meteo archive, hourly temperature_2m, "
                               f"max over local {WINDOW[0]}:00-{WINDOW[1]}:00",
        "seasonal_window": {"centre_doy": centre_doy, "half_width_days": half},
        "source_snapshot": snap["snapshot_id"],
        "stations": out,
    }
    p = os.path.join(a.repo, "data", "debias_om.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(doc, open(p, "w"), indent=1, sort_keys=True)
    print("-" * 88)
    print(f"\nwrote data/debias_om.json — {len(out)} stations")
    if skipped:
        print("skipped: " + "; ".join(skipped))

    big = sorted(out.items(), key=lambda kv: -abs(kv[1]["delta_vs_wxdb"] or 0))[:5]
    print("\nlargest disagreements with wx.db's fcst_raw-based offset:")
    for s, v in big:
        if v["delta_vs_wxdb"] is None:
            continue
        print(f"  {v['display']:<14}{v['debias_c']:+.2f} here vs {v['wxdb_debias_median']:+.2f} "
              f"in wx.db   (delta {v['delta_vs_wxdb']:+.2f})")
    print("\nwidest residual spread — these are the stations whose bucket tail is most")
    print("likely understated, regardless of how well centred the median is:")
    for s, v in sorted(out.items(), key=lambda kv: -kv[1]["sd"])[:5]:
        print(f"  {v['display']:<14}sd {v['sd']:.2f} °C   p10..p90 {v['p10']:+.2f}..{v['p90']:+.2f}"
              f"   {v['resid_ge2_share']*100:.1f}% of days >= +2 over the de-biased forecast")


if __name__ == "__main__":
    main()
