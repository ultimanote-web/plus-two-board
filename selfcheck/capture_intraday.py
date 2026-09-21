#!/usr/bin/env python3
"""
capture_intraday.py — price AND thermometer, several times through the local day.

Why this exists
---------------
Everything this project has measured says the market's price is calibrated at board
time (~T−30h). That is not the same claim at T−11h, when roughly two thirds of the
day's heating has already happened and the current reading is *observable*. On
2026-09-21 the Qingdao 30 °C bucket was priced 13.1% in the morning capture and 3.8%
eleven hours before resolution; Wuhan 27 °C went 23.8% → 7.6%. Whether that residual
is correctly priced is an open question, and it is the only open question in this
project resting on a physical mechanism rather than a fitted pattern.

Answering it needs something the pipeline has never collected: **what the thermometer
actually said at the moment of decision**, and how much heating was left. Forecasts
and prices are not enough — the whole point is that by midday the forecast has been
superseded by an observation.

    python3 selfcheck/capture_intraday.py              # every city, its own local day
    python3 selfcheck/capture_intraday.py --cities tokyo,seoul

Per city per run this records:
  * the full ladder (raw), plus the usual mode / cum_up2 / cum_dn2 summary
  * the day's **maximum observed so far** at the resolving ICAO, from METAR
  * the latest observation, wind direction and speed, precipitation, cloud
  * local hour, hours of daylight remaining, and the headroom from the current max
    to the +2 bucket — the physical quantity the trade actually depends on

Trading day is each city's **own local date**, not the UTC date. Tokyo's "September 21"
market is live from 15:00 UTC on the 20th to 15:00 UTC on the 21st; keying on UTC would
silently mix two different markets in one row.

Writes ladders/intraday/YYYY-MM-DD/HHMMz.json (raw, per capture) and appends one row
per city to log/intraday.csv, idempotent on (date, city, captured_utc).

Observations come from aviationweather.gov METAR — the resolving station's own
readings, not a model. Open-Meteo's hourly series is the fallback and is flagged as
such in `obs_source`, because its "past" hours are model output, and this project has
already been bitten once by treating a model value as a station reading.
"""
import argparse, csv, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMMA = "https://gamma-api.polymarket.com/events?slug=highest-temperature-in-{city}-on-{month}-{day}-2026"
METAR = "https://aviationweather.gov/api/data/metar?ids={ids}&format=json&hours={hours}&taf=false"
OM = ("https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lons}"
      "&hourly=temperature_2m&daily=sunset,sunrise&timezone=auto&forecast_days=2")
MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")

COLS = ["date", "city", "icao", "captured_utc", "local_hour", "hours_to_sunset",
        "obs_source", "obs_n", "obs_max", "obs_max_utcday", "obs_latest", "obs_latest_utc",
        "wind_dir", "wind_kt", "precip_mm", "cloud_pct",
        "n_buckets", "book_sum", "mode", "mode_p", "top_open", "bot_open",
        "cum_up2", "cum_dn2", "bid_up2", "ask_up2", "depth_up2",
        "bid_dn2", "ask_dn2", "depth_dn2", "headroom_up2", "headroom_mode"]


def get(url, tries=3, pause=0.25, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.loads(r.read().decode())
            time.sleep(pause)
            return out
        except Exception as e:
            if i == tries - 1:
                print(f"  ! {url[:110]}: {e}", file=sys.stderr)
                return None
            time.sleep(2 * (i + 1))


def num(x, d=0.0):
    try:
        v = float(x)
        return d if v != v else v
    except (TypeError, ValueError):
        return d


def bucket_num(title):
    digits = ""
    for ch in title:
        if ch.isdigit() or (ch == "-" and not digits):
            digits += ch
        elif digits:
            break
    return int(digits) if digits else None


def open_ended(t):
    t = (t or "").lower()
    return ("higher" in t) or ("above" in t) or ("below" in t) or ("lower" in t)


# ---------------------------------------------------------------- observations

def fetch_metar(icaos, hours=18):
    """One call for every station. Returns {icao: [ {t, temp, wdir, wspd, cloud, precip} ]}."""
    js = get(METAR.format(ids=",".join(icaos), hours=hours), timeout=45)
    if not isinstance(js, list):
        return {}
    out = {}
    for m in js:
        icao = (m.get("icaoId") or "").upper()
        if not icao:
            continue
        t = m.get("obsTime")
        temp = m.get("temp")
        if t is None or temp is None:
            continue
        clouds = m.get("clouds") or []
        # METAR cover codes to a rough percentage; SKC/CLR 0, FEW 20, SCT 40, BKN 75, OVC 100
        cover = {"SKC": 0, "CLR": 0, "CAVOK": 0, "NCD": 0,
                 "FEW": 20, "SCT": 40, "BKN": 75, "OVC": 100, "VV": 100}
        pct = max([cover.get((c.get("cover") or "").upper(), 0) for c in clouds], default=None)
        out.setdefault(icao, []).append({
            "t": int(t), "temp": num(temp, None) if temp is not None else None,
            "wdir": m.get("wdir"), "wspd": m.get("wspd"),
            "cloud": pct, "precip": m.get("precip"),
        })
    for v in out.values():
        v.sort(key=lambda r: r["t"])
    return out


def fetch_openmeteo(stations, order):
    """One call for every station: hourly temperature and today's sunset, local time."""
    lats = ",".join(f"{stations[c]['lat']}" for c in order)
    lons = ",".join(f"{stations[c]['lon']}" for c in order)
    js = get(OM.format(lats=lats, lons=lons), timeout=45)
    if js is None:
        return {}
    blocks = js if isinstance(js, list) else [js]
    out = {}
    for c, b in zip(order, blocks):
        try:
            out[c] = {
                "offset": int(b.get("utc_offset_seconds") or 0),
                "times": b["hourly"]["time"],
                "temps": b["hourly"]["temperature_2m"],
                "sunset": b["daily"]["sunset"],
            }
        except Exception:
            continue
    return out


def observations(city, st, om, metar, now_utc):
    """The day so far at the resolving station, in the city's own local day."""
    o = om.get(city)
    offset = o["offset"] if o else 0
    local = now_utc + timedelta(seconds=offset)
    local_midnight_utc = (local.replace(hour=0, minute=0, second=0, microsecond=0)
                          - timedelta(seconds=offset))

    hours_to_sunset = None
    if o:
        for s in o["sunset"]:
            try:
                ss = datetime.fromisoformat(s)           # local naive
            except ValueError:
                continue
            if ss.date() == local.date():
                hours_to_sunset = round((ss - local.replace(tzinfo=None)).total_seconds() / 3600, 2)
                break

    all_rows = [r for r in metar.get(st["icao"].upper(), []) if r["temp"] is not None]
    rows = [r for r in all_rows
            if datetime.fromtimestamp(r["t"], timezone.utc) >= local_midnight_utc]

    # The market text says "the highest reading under the Temp column for all times on
    # this day" and links weather.gov's station timeseries, which can be read in UTC or
    # in local time. Which one it means changes obs_max for every city not on UTC, and
    # guessing would put a silent error under every row. So both are recorded and the
    # proxy check reports which agrees with the settlements. Measure, don't assume.
    utc_midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0,
                                                      microsecond=0)
    urows = [r for r in all_rows
             if datetime.fromtimestamp(r["t"], timezone.utc) >= utc_midnight]
    umax = round(max(r["temp"] for r in urows), 1) if urows else ""

    if rows:
        last = rows[-1]
        return {
            "obs_source": "metar", "obs_n": len(rows),
            "obs_max": round(max(r["temp"] for r in rows), 1),
            "obs_max_utcday": umax,
            "obs_latest": round(last["temp"], 1),
            "obs_latest_utc": datetime.fromtimestamp(last["t"], timezone.utc)
                              .isoformat(timespec="seconds"),
            "wind_dir": last["wdir"] if isinstance(last["wdir"], (int, float)) else "",
            "wind_kt": last["wspd"] if isinstance(last["wspd"], (int, float)) else "",
            "precip_mm": last["precip"] if isinstance(last["precip"], (int, float)) else "",
            "cloud_pct": last["cloud"] if last["cloud"] is not None else "",
            "local_hour": round(local.hour + local.minute / 60, 2),
            "hours_to_sunset": hours_to_sunset if hours_to_sunset is not None else "",
        }

    # Fallback: Open-Meteo's hourly series. Its past hours are MODEL values, not station
    # readings — flagged so no analysis can silently mix the two.
    if o:
        mx, n, latest = None, 0, None
        for ts, tv in zip(o["times"], o["temps"]):
            try:
                h = datetime.fromisoformat(ts)
            except ValueError:
                continue
            if h.date() != local.date() or h > local.replace(tzinfo=None) or tv is None:
                continue
            n += 1; latest = tv
            mx = tv if mx is None else max(mx, tv)
        if n:
            return {"obs_source": "open_meteo_model", "obs_n": n,
                    "obs_max": round(mx, 1), "obs_max_utcday": umax,
                    "obs_latest": round(latest, 1),
                    "obs_latest_utc": "", "wind_dir": "", "wind_kt": "",
                    "precip_mm": "", "cloud_pct": "",
                    "local_hour": round(local.hour + local.minute / 60, 2),
                    "hours_to_sunset": hours_to_sunset if hours_to_sunset is not None else ""}

    return {"obs_source": "none", "obs_n": 0, "obs_max": "", "obs_max_utcday": umax,
            "obs_latest": "",
            "obs_latest_utc": "", "wind_dir": "", "wind_kt": "", "precip_mm": "",
            "cloud_pct": "", "local_hour": round(local.hour + local.minute / 60, 2),
            "hours_to_sunset": hours_to_sunset if hours_to_sunset is not None else ""}


# ---------------------------------------------------------------------- ladder

def read_ladder(city, d):
    ev = get(GAMMA.format(city=city, month=MONTHS[d.month - 1], day=d.day))
    if not ev:
        return None
    ms = ev[0].get("markets", [])
    if len(ms) < 5 or any("°F" in (m.get("groupItemTitle") or "") for m in ms):
        return None
    rungs = []
    for m in ms:
        t = m.get("groupItemTitle") or ""
        b, a = round(num(m.get("bestBid")), 4), round(num(m.get("bestAsk")), 4)
        rungs.append({"title": t, "deg": bucket_num(t), "open": open_ended(t),
                      "bid": b, "ask": a, "mid": round((b + a) / 2, 4),
                      "liq": round(num(m.get("liquidityNum")), 2),
                      "vol": round(num(m.get("volumeNum")), 2)})
    return rungs


def summarize(rungs):
    tot = sum(r["mid"] for r in rungs)
    if tot <= 0:
        return None
    for r in rungs:
        r["p"] = r["mid"] / tot
    mi = max(range(len(rungs)), key=lambda i: rungs[i]["p"])
    mode = rungs[mi]["deg"]
    if mode is None:
        return None

    def at(off):
        want = mode + off
        for r in rungs:
            if r["deg"] == want and not r["open"]:
                return r
        for r in rungs:
            if r["deg"] == want:
                return r
        return None

    up2, dn2 = at(+2), at(-2)
    return {
        "n_buckets": len(rungs), "book_sum": round(tot, 4),
        "mode": mode, "mode_p": round(rungs[mi]["p"], 4),
        "top_open": int(bool(rungs[-1]["open"])), "bot_open": int(bool(rungs[0]["open"])),
        "cum_up2": round(sum(r["p"] for r in rungs
                             if r["deg"] is not None and r["deg"] >= mode + 2), 4),
        "cum_dn2": round(sum(r["p"] for r in rungs
                             if r["deg"] is not None and r["deg"] <= mode - 2), 4),
        "bid_up2": up2["bid"] if up2 else "", "ask_up2": up2["ask"] if up2 else "",
        "depth_up2": int(up2["liq"]) if up2 else "",
        "bid_dn2": dn2["bid"] if dn2 else "", "ask_dn2": dn2["ask"] if dn2 else "",
        "depth_dn2": int(dn2["liq"]) if dn2 else "",
    }


# ------------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=ROOT)
    ap.add_argument("--cities", default=None)
    ap.add_argument("--metar-hours", type=int, default=30)  # must span a local day AND a UTC day
    a = ap.parse_args()

    inputs_path = os.path.join(a.repo, "data", "latest.json")
    if not os.path.exists(inputs_path):
        sys.exit("no data/latest.json — the droplet export has not run")
    stations = json.load(open(inputs_path))["stations"]
    cities = [c.strip() for c in a.cities.split(",")] if a.cities else sorted(stations)
    cities = [c for c in cities if c in stations]
    if not cities:
        sys.exit("no cities")

    now = datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")

    # two batched calls cover every station's weather; the ladders are per city
    metar = fetch_metar([stations[c]["icao"].upper() for c in cities], a.metar_hours)
    om = fetch_openmeteo(stations, cities)
    print(f"metar: {len(metar)} stations   open-meteo: {len(om)} stations")

    raw, rows, skipped = {}, [], []
    for c in cities:
        st = stations[c]
        obs = observations(c, st, om, metar, now)
        o = om.get(c)
        local_date = (now + timedelta(seconds=(o["offset"] if o else 0))).date()

        rungs = read_ladder(c, local_date)
        if not rungs:
            skipped.append(c); continue
        s = summarize(rungs)
        if not s:
            skipped.append(c); continue

        omax = obs["obs_max"]
        head2 = round((s["mode"] + 2) - omax, 1) if isinstance(omax, (int, float)) else ""
        headm = round(s["mode"] - omax, 1) if isinstance(omax, (int, float)) else ""

        raw[c] = {"icao": st["icao"], "local_date": local_date.isoformat(),
                  "obs": obs, "ladder": rungs}
        rows.append({"date": local_date.isoformat(), "city": c, "icao": st["icao"],
                     "captured_utc": stamp, **obs, **s,
                     "headroom_up2": head2, "headroom_mode": headm})

    hh = now.strftime("%H%Mz")
    d = os.path.join(a.repo, "ladders", "intraday", now.date().isoformat())
    os.makedirs(d, exist_ok=True)
    json.dump({"captured_utc": stamp, "cities": raw, "skipped": skipped},
              open(os.path.join(d, f"{hh}.json"), "w"), indent=1, sort_keys=True)

    lp = os.path.join(a.repo, "log", "intraday.csv")
    os.makedirs(os.path.dirname(lp), exist_ok=True)
    seen = set()
    if os.path.exists(lp):
        seen = {(r["date"], r["city"], r["captured_utc"]) for r in csv.DictReader(open(lp))}
    new = 0
    with open(lp, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        if not seen:
            w.writeheader()
        for r in sorted(rows, key=lambda x: x["city"]):
            if (r["date"], r["city"], r["captured_utc"]) in seen:
                continue
            w.writerow(r); new += 1

    src = {}
    for r in rows:
        src[r["obs_source"]] = src.get(r["obs_source"], 0) + 1
    print(f"{stamp}: {len(rows)} cities, skipped {len(skipped)}"
          + (f" ({', '.join(skipped)})" if skipped else ""))
    print(f"observation sources: {src}")
    print(f"appended {new} rows to log/intraday.csv")

    live = [r for r in rows if isinstance(r["hours_to_sunset"], (int, float))
            and 0 <= r["hours_to_sunset"] <= 6 and isinstance(r["headroom_up2"], (int, float))]
    if live:
        print(f"\n{len(live)} cities within 6h of sunset:")
        for r in sorted(live, key=lambda x: x["headroom_up2"]):
            print(f"  {r['city']:14s} local {r['local_hour']:5.2f}  max so far {r['obs_max']:5.1f}"
                  f"  mode {r['mode']:3d}  +2 bucket needs +{r['headroom_up2']:.1f}C"
                  f"  quoted {r['bid_up2']}")


if __name__ == "__main__":
    main()
