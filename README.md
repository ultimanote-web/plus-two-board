# plus-two-board

Public data channel and self-check for the nightly Plus-Two Board — the +2 bucket NO
sale on Polymarket daily "Highest temperature in \<city\>" °C markets.

**This repo is public and carries model inputs only.** No fills, no sizes, no account
state, nothing about what was actually traded. Keep it that way.

---

## Why it exists

Two problems, one repo.

**1. The board cannot reach `wx.db`.** The environment that builds the board has no
route to the droplet — SSH, the DigitalOcean API, Telegram, S3 and pastebin are all
blocked by its egress proxy. `raw.githubusercontent.com` is reachable. So the bot
publishes here and the board reads from here.

**2. The board could not check itself.** Settlements were being scraped by hand, which
means they were scraped when someone remembered. A tripwire nobody runs is not a
tripwire. The self-check runs on a schedule on GitHub's runners — which *do* have
internet — and fails the build when the numbers say stop.

---

## Layout

```
data/YYYY-MM-DD.json     bot writes: de-bias offsets, tail snapshot, settled outcomes
data/latest.json         convenience copy of the newest
predictions/YYYY-MM-DD.json   what the board said, before the day ran
settled/YYYY-MM-DD.json       what the stations actually read
log/settlements.csv      append-only. never rewritten, never rolled back.
selfcheck/report.json    output of the audit — the board reads this too
STATUS.md                human-readable: current calibration and halt state
```

`data/` is date-stamped rather than a single rolling file for two reasons: the board's
fetcher caches 15 minutes per URL, so a stable filename can serve stale numbers; and an
append-only history is what a settlement log is supposed to be.

---

## The three moving parts

### `bot/export_board_inputs.py` — runs on the droplet

Reads `wx.db`, writes `data/YYYY-MM-DD.json`, commits, pushes. Cron it after the
nightly `wxfeatures` pass.

```bash
python3 bot/export_board_inputs.py --db /opt/wx/wx.db --repo /opt/plus-two-board --push
```

**Set `debias_sign` correctly and explicitly.** `actual_minus_forecast` means a
positive offset says the station reads *hotter* than Open-Meteo predicted. Get this
backwards and every model gap flips sign, which is the difference between a row
carrying a 22-point penalty and carrying none. The schema requires the field; the
self-check refuses a file without it.

### `selfcheck/fetch_settlements.py` — runs on GitHub

Pulls resolved outcomes for a date from Polymarket Gamma into `settled/YYYY-MM-DD.json`
and appends to `log/settlements.csv`. Skips city-days already logged, so re-running is
safe.

### `selfcheck/check.py` — runs on GitHub

The audit. Reports, and exits non-zero on a tripwire:

| Check | Tripwire |
|---|---|
| Selected-row +2 settlements | binomial P(≥k \| tails correct) < 2% |
| Field calibration | realized rate outside the Wilson interval of predicted |
| Per-city repeat losses | any city losing twice inside 14 days |
| Board size trend | trailing-4-week mean picks/day declining two reviews running |
| Provisional gate expiry | any gate past its `expires` date |
| Data integrity | a settled bucket the logged ladder did not contain |

A failing check writes `STATUS.md` with `HALTED` and a reason. That file is the signal —
the board reads it before building and refuses to publish a selection while it says
halted.

---

## Current state — seeded 2026-09-12

**HALTED.** 3 of the 7 rows the board has put forward settled at exactly +2, against
0.35 expected. P(≥3 | the tails are right) = **0.37%**.

| Date | City | Tail | Result |
|---|---|---|---|
| Sep 9 | Munich | 8.3% | **lost** |
| Sep 10 | Shenzhen | 4.7% | **lost** |
| Sep 10 | Tokyo | 5.2% | won |
| Sep 10 | Cape Town | 4.5% | won |
| Sep 12 | Seoul | 2.1% | won |
| Sep 12 | Shenzhen | 4.7% | **lost** |
| Sep 12 | Tokyo | 5.2% | won |

There is a common cause and it is one station: **Shenzhen is 2 of the 3 losses**, both
landing exactly on mode+2. On Sep 12 Open-Meteo forecast the ZGSZ Bao'an max at
31.1 °C with 2.6 mm of rain under 89% cloud; the station read **34 °C**. A +2.9 °C
error in the hot direction on a day forecast wet and overcast is the model being wrong
about the weather type, not the temperature.

The station is not the problem — the market resolves on
`weather.gov/wrh/timeseries?site=zgsz`, which is the coordinate the forecast was fetched
for. So this is forecast bias at that station, which is precisely what the `debias_c`
offsets in `data/` are for. **That export is the unblock.**

Counter-evidence worth keeping: the field as a whole is fine. Over Sep 9–10, 3 of 64
priced city-days settled at ≥+2 against 4.70 expected. The tails are not broadly
broken — something specific is.

One gate paid for itself on Sep 12: **open top**. Karachi settled at "36 °C or higher",
its +2 slot, and would have been a loss. It was the best-priced row on the board at
3.00×, and the gate excluded it.

---

## Setup — the whole runbook

The design goal is **one cron on the droplet**. The droplet is the only machine with
`wx.db`, so that is the only job that has to live there; everything downstream runs on
GitHub's runners, which have internet and need no secrets.

```
droplet          GitHub Actions                        you + Claude
────────         ──────────────                        ────────────
wx.db
  │ export_board_inputs.py (04:15 UTC, cron)
  ▼
data/YYYY-MM-DD.json ──► build_predictions.py (04:30) ──► predictions/YYYY-MM-DD.json
                              │                                  │
                              │                                  └──► the published board
                              ▼
                         fetch_settlements.py (06:00, 16:00) ──► settled/ + log/
                              │
                              ▼
                         check.py ──► STATUS.md + selfcheck/report.json
```

### Step 1 — push the repo (5 minutes)

```bash
cd plus-two-board
git init && git add . && git commit -m "initial: schema, exporter, self-check, seeded log"
gh repo create plus-two-board --public --source=. --push
```

Both workflows go live immediately. The self-check will run and **fail** — that is
correct, the seeded record is a halt. `STATUS.md` appears in the repo root.

### Step 2 — give the droplet write access

Do this yourself; never paste a key into a chat.

```bash
ssh-keygen -t ed25519 -C "plus-two-board droplet" -f ~/.ssh/ptb_deploy -N ""
cat ~/.ssh/ptb_deploy.pub      # → GitHub → repo → Settings → Deploy keys → Add,
                               #    tick "Allow write access"
```

```bash
# on the droplet
cat >> ~/.ssh/config <<'EOF'
Host github-ptb
  HostName github.com
  User git
  IdentityFile ~/.ssh/ptb_deploy
EOF
git clone github-ptb:<you>/plus-two-board /opt/plus-two-board
cd /opt/plus-two-board
git config user.email "bot@users.noreply.github.com"
git config user.name  "wx bot"
```

A deploy key is scoped to this one repo and can be revoked on its own. A personal
access token on the droplet can reach everything you own; if you use one anyway, make
it fine-grained and scope it to this repository only.

### Step 3 — the one cron

```bash
# verify the sign convention FIRST — see below
python3 /opt/plus-two-board/bot/export_board_inputs.py --db /opt/wx/wx.db
cat /opt/plus-two-board/data/latest.json | head -40     # eyeball it

crontab -e
# 15 4 * * *  cd /opt/plus-two-board && git pull -q && \
#             python3 bot/export_board_inputs.py --db /opt/wx/wx.db --push \
#             >> /var/log/ptb-export.log 2>&1
```

### Step 4 — verify `debias_sign` before trusting a single gap

This is the one setting that silently inverts the board. `DEBIAS_SIGN` at the top of
`export_board_inputs.py` says what the number means; the exporter computes
`actual − forecast`, so `actual_minus_forecast` is correct **for that code**. If you
swap in your own offsets from elsewhere, check them against a day you remember.

Sanity test: Shenzhen on 2026-09-12 forecast 31.1 °C, actual 34 °C. A correct
`actual_minus_forecast` offset for ZGSZ is **positive**. If the export produces a
negative number there, the sign is backwards and every model gap on the board is wrong.

### Step 5 — watch one number for a week

`STATUS.md`. Nothing else. It is the only artifact that says whether to trade.

---

## What is still manual, and honestly should stay that way

The board's **judgement half** — the verdict, the per-row note, which exclusion is
genuinely arguable, which row is the day's warning rather than the day's trade. A
script that generates those is a script inventing reasoning it cannot produce. The
pipeline emits the numbers; the board is written from them.

What automation buys is that the numbers are always there, always logged, and always
checked — so the judgement is applied to a complete record instead of to whatever was
scraped by hand that evening.
