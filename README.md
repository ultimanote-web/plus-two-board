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
ladders/YYYY-MM-DD.json  every bucket of every city's book at board time — raw
log/ladders.csv          derived one-row-per-city-day summary of the above
ladders/intraday/DATE/HHMMz.json   ladder + thermometer, four times a day
log/intraday.csv         derived: price, observed max so far, hours to sunset, headroom
log/trades.csv           real fills, appended by hand. the only file recording what was DONE.
selfcheck/report.json    output of the audit — the board reads this too
STATUS.md                human-readable: current calibration and halt state
research/               pre-registrations and results. see below.
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

### `selfcheck/capture_ladders.py` — runs on GitHub, inside the board job

Records the full price ladder for **every** city, including rows no gate would pass.
`predictions/` already stores a price, but only for the +2 bucket of rows that survived
the gates — the selected subset, which is the one sample that cannot be used to ask
whether the selector is wrong. Raw into `ladders/`, derived into `log/ladders.csv`,
idempotent on `(date, city)`.

### `selfcheck/capture_intraday.py` — runs on GitHub, 00/06/12/18 UTC

Price **and** thermometer, keyed to each city's own local date. Records the day's
maximum observed so far at the resolving ICAO (METAR, with Open-Meteo model values as a
flagged fallback), hours to local sunset, and `headroom_up2` — how many degrees the
temperature still has to climb for the +2 bucket to hit.

This is the only part of the pipeline that logs what the thermometer actually said at
the moment of decision, rather than what a model predicted the day before. It exists
because the one open hypothesis with a physical mechanism behind it — that late-day
residual prices lag a collapsing uncertainty — cannot be tested without it.

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

## Current state — 2026-09-21

**HALTED**, and the diagnosis has moved on from where this section started.

| | |
|---|---|
| selected rows settling at +2 | **6 of 34 (18%)** against 1.3 expected, P = 0.17% |
| whole field | 14 of 349 (4.0%) against 7.6% predicted, t = −2.41 |
| tail terciles | low band 7 hits/116, high band **3/117 against 13.9 expected** |

The field settles *calmer* than predicted while the selected subset settles five times
hotter. That is not a broken station or a bad season — it is **adverse selection built
into the selection rule**. Requiring `break-even ÷ tail > 1` selects exactly the rows
where the price implies more risk than `bt_daily` does, and the price keeps being
right. No gate repairs it, because the gate *is* the selector.

Four independent tests now agree (see `research/`): gap trading null, the market's mode
calibrated, cities statistically indistinguishable from one population, and price bands
tracking their own break-evens across the whole range. The simplest description
consistent with all four is that these ladders are efficiently priced at board horizon.

**What is still open:** whether that holds *inside the local afternoon*, when the day's
maximum is partly observable. Registered, running, reads 2026-10-31.

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

## `research/` — what has been tested, and what is being tested

Every file here is either a pre-registration written before its data existed, or the
result read against thresholds fixed in that registration. A result with no matching
pre-registration is a story, not a finding.

| file | status |
|---|---|
| `prereg-tail-adjudication.md` | registered 2026-09-13; **read 2026-09-20** at k ≥ 5 / k ≤ 1 |
| `gap-test-result.md` | run 2026-09-19. Gap trading dead (slope −0.04). Mode calibrated (46.1% vs 45.7%). Left skew found: P(dev ≤ −2) = 7.0% against P(dev ≥ +2) = 3.7% |
| `prereg-asymmetry-pricing.md` | registered 2026-09-19; **read 2026-10-19** at 150 joined city-days |
| `no-calm-cities.md` | run 2026-09-21. Cities are one population at 4.0% (homogeneity p = 0.245). City selection is dead. |
| `gate-value.md` | run 2026-09-21. Every gate measured. Only the price discriminates (AUC 0.78) and it says the market is right; price bands track break-even |
| `prereg-late-day-residual.md` | registered 2026-09-21; **read 2026-10-31** at 800 qualifying city-days |
| `analyze_asymmetry.py`, `analyze_late_day.py` | run with every self-check; each refuses to conclude below its registered sample |

The +2 board is **halted** and nothing above changes that. `log/trades.csv` records
real fills and is **not** a test of anything — it is self-selected, so it can measure
what was done but never whether the rule behind it works. The diagnosis was adverse
selection built into the selection rule — requiring `break-even ÷ tail > 1` selects
exactly the rows where the price implies more risk than `bt_daily` does, and over 207
city-days the price was right. No gate repairs this, because the gate *is* the selector.

---

## What is still manual, and honestly should stay that way

The board's **judgement half** — the verdict, the per-row note, which exclusion is
genuinely arguable, which row is the day's warning rather than the day's trade. A
script that generates those is a script inventing reasoning it cannot produce. The
pipeline emits the numbers; the board is written from them.

What automation buys is that the numbers are always there, always logged, and always
checked — so the judgement is applied to a complete record instead of to whatever was
scraped by hand that evening.
