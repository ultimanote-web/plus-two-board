#!/usr/bin/env python3
"""
check_provenance.py — does the forecast the board computes match the forecast the
backtest measured?

This is the question the whole de-bias rests on. bt_daily.fcst_raw is what the tails
and the debias_median were measured against. The board computes its own forecast live
from Open-Meteo as the max over local 11:00-17:00. If those two are the same quantity,
the offset transfers and applying it corrects bias. If they are NOT — if fcst_raw is,
say, a fixed-hour value or a different window — then applying the offset does not
correct anything, it injects the difference between the two definitions as a fresh
error, and it does so invisibly.

    python3 bot/check_provenance.py --db /root/wxbot/wx.db --days 20

Reads bt_daily for recent dates, re-fetches the archived Open-Meteo forecast for the
same station and date, reduces it the way the board does, and reports the difference.

Reading the result:
  * mean |diff| under ~0.3 °C, no trend  -> same quantity. The offsets transfer.
  * a consistent offset of its own       -> different quantity, but a stable mapping.
                                            Fixable, but the board must apply THAT too.
  * large and scattered                  -> different quantity. Do not apply the offsets
                                            until it is understood.
"""
import argparse, json, os, sqlite3, statistics, sys, time, urllib.request
from datetime import date, timedelta

ARCHIVE = ("https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
           "&hourly=temperature_2m&start_date={d}&end_date={d}&timezone=auto")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOW = (11, 17)


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if i == tries - 1:
                print(f"  ! {e}", file=sys.stderr)
                return None
            time.sleep(2 * (i + 1))


def window_max(j, lo, hi):
    h = (j or {}).get("hourly") or {}
    t = h.get("time") or []
    v = h.get("temperature_2m") or []
    vals = [v[i] for i, s in enumerate(t)
            if len(s) >= 13 and lo <= int(s[11:13]) <= hi and v[i] is not None]
    return max(vals) if vals else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/root/wxbot/wx.db")
    ap.add_argument("--days", type=int, default=20)
    ap.add_argument("--cities", default="Shenzhen,Seoul,Tokyo,Chongqing,Paris,London")
    a = ap.parse_args()

    meta = json.load(open(os.path.join(ROOT, "schema", "stations.json")))["stations"]
    cx = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)

    print(f"{'city':<14}{'icao':<6}{'rows':>5}{'mean fcst_raw':>15}{'mean OM 11-17':>15}"
          f"{'mean diff':>11}{'med diff':>10}{'max |diff|':>12}")
    print("-" * 88)

    overall = []
    for city in [c.strip() for c in a.cities.split(",") if c.strip()]:
        rows = cx.execute(
            "SELECT obs_date, icao, fcst_raw FROM bt_daily "
            "WHERE city=? AND unit='C' AND fcst_raw IS NOT NULL "
            "ORDER BY obs_date DESC LIMIT ?", (city, a.days)).fetchall()
        if not rows:
            print(f"{city:<14}  no rows"); continue
        icao = rows[0][1]
        if icao not in meta:
            print(f"{city:<14}{icao:<6}  no coordinates"); continue
        lat, lon = meta[icao]["lat"], meta[icao]["lon"]

        diffs, mine, theirs = [], [], []
        for obs_date, _, fr in rows:
            j = get(ARCHIVE.format(lat=lat, lon=lon, d=obs_date))
            m = window_max(j, *WINDOW)
            time.sleep(0.3)
            if m is None:
                continue
            diffs.append(m - float(fr)); mine.append(m); theirs.append(float(fr))
        if not diffs:
            print(f"{city:<14}{icao:<6}  no archive data"); continue

        overall += diffs
        print(f"{city:<14}{icao:<6}{len(diffs):>5}{statistics.mean(theirs):>15.2f}"
              f"{statistics.mean(mine):>15.2f}{statistics.mean(diffs):>+11.2f}"
              f"{statistics.median(diffs):>+10.2f}{max(abs(d) for d in diffs):>12.2f}")

    cx.close()
    if overall:
        m = statistics.mean(overall)
        am = statistics.mean(abs(d) for d in overall)
        print("-" * 88)
        print(f"\nall cities: n={len(overall)}  mean diff {m:+.2f} °C  "
              f"mean |diff| {am:.2f} °C  sd {statistics.pstdev(overall):.2f}")
        print()
        if am < 0.3:
            print("  SAME QUANTITY. The de-bias offsets transfer; apply them.")
        elif abs(m) > 0.5 and am - abs(m) < 0.3:
            print(f"  DIFFERENT QUANTITY, STABLE OFFSET of {m:+.2f} °C. The board must")
            print("  account for this separately before the de-bias means anything.")
        else:
            print("  DIFFERENT QUANTITY, UNSTABLE. Do NOT apply the offsets until this")
            print("  is understood — they would inject error rather than remove it.")
        print("\n  Note: this compares the live archive against a stored forecast. Open-Meteo's")
        print("  archive is a reanalysis of the same model, not the original run, so a small")
        print("  residual is expected even when the definitions match exactly.")


if __name__ == "__main__":
    main()
