# Milan crowd radar — notes for Claude

A daily radar of the events in Milan that bring crowds from outside and put
pressure on **taxis** and **Linate airport**: trade fairs (Fiera Milano Rho),
congresses (Allianz MiCo), San Siro matches, arena concerts (Unipol Dome,
Unipol Forum), transport strikes, holidays. The owner uses it to plan around
taxi and airport rushes and shares it with friends.

Live outputs:
- **Web app** — https://davidev886.github.io/milan-crowd-radar/ (GitHub Pages, `main`, root)
- **Telegram bot** — sends a brief at ~07:07 and a tomorrow preview at ~19:07 Milan time

This repo is **public**. Never commit tokens, chat ids, Telegram usernames or
private links. Secrets live only in GitHub Actions secrets.

## Before you change anything

1. `git pull --rebase origin main` — a cloud routine commits new data to `main`
   every morning around 06:45 Milan time, so local copies go stale daily.
2. Don't hand-edit `data/*.json` expecting it to stick: the routine rebuilds
   both files every morning from its own copy (see "Outside this repo"). For a
   lasting data change, change the routine's prompt (`/schedule update`) or tell
   the owner it will be overwritten.
3. Keep the data schema stable. The bot, the web app and the routine all depend
   on it; a schema change means updating all three.

## How it fits together

```
cloud routine "Milan crowd radar – morning refresh" (daily 06:40 Europe/Rome)
  researches events + strikes + weather on the web
  ├─▶ updates a private claude.ai dashboard (link is in the routine's prompt)
  └─▶ commits data/events.json + data/briefing.json to main
          ├─▶ GitHub Pages redeploys index.html automatically (~1 min)
          └─▶ .github/workflows/telegram-brief.yml reads them at 07:07 / 19:07
                └─▶ bot/send_brief.py ─▶ Telegram (chats in secret TELEGRAM_CHAT_ID)
```

## Files

| Path | What it is |
|---|---|
| `index.html` | The whole web app: inline CSS + JS, no build step, no dependencies. Fetches `data/*.json` with relative URLs. |
| `manifest.webmanifest`, `icon*.png`, `icon.svg`, `apple-touch-icon.png` | Add-to-home-screen support. |
| `.nojekyll` | Stops GitHub Pages from running Jekyll. Keep it. |
| `bot/send_brief.py` | Builds and sends the Telegram messages. Python standard library only. |
| `.github/workflows/telegram-brief.yml` | Scheduled + manual runs of the bot. |
| `data/events.json` | List of events (schema below). Written by the routine. |
| `data/briefing.json` | One written note per day, today + 7 days. Written by the routine. |
| `README.md` | Human-facing overview and Telegram setup steps. |

## Data schema

`data/events.json` — array of objects, all keys required:

| key | notes |
|---|---|
| `id` | unique, `[a-z0-9_]` |
| `start`, `end` | `YYYY-MM-DD`, Milan dates, `start <= end` |
| `when` | display text, e.g. `Thu 5 – Sun 8 Nov` |
| `time`, `name`, `venue`, `zone`, `crowd`, `peak`, `tip`, `status` | display text (`status`: Confirmed, Time TBC, Announced, In MIT strike register…) |
| `category` | one of `Fair`, `Congress`, `Football`, `Concert`, `Strike`, `Holiday`, `Culture` |
| `outside` | `High` / `Medium` / `Low` / `—` — share of visitors from outside Milan |
| `taxi`, `linate` | integers 1–5 (estimates) |
| `source` | `https://` URL the date was checked against |

`data/briefing.json` — array of `{date, headline, taxi, linate, weather}`, one
per day from today to today+7. `weather` may be `""`.

**Impact guide.** taxi 5 = strike hitting taxis/ATM, or 100k+ people over the
day (EICMA public days, Artigiano in Fiera, derby); 4 = 60–75k stadium crowd or
big international crowd; 3 = arena concert (12–16k) or large fair/congress;
2 = smaller; 1 = minor. linate 4–5 = congress delegates, international trade
visitors, long weekends, airport or ATM strikes (M4 serves Linate); 1 = local crowd.

**Pressure (0–5)** for a day = highest `taxi` or `linate` among that day's
events, +1 when three or more events overlap, capped at 5. The same rule is
implemented in `index.html` (`pressure()`) and `bot/send_brief.py`
(`pressure()`); keep them identical. The page's `pressure()` also takes an
optional `keys` list (`['taxi']` or `['linate']`) for the per-mode scores and
the calendar's Taxi / Linate switch; its default call is the shared rule above
and must keep matching the bot. The page's "Refreshed…" line is derived from the
first `briefing.json` date (the routine's run day), so keep that file starting today.

## Run and test locally

```bash
python3 bot/send_brief.py --dry-run                         # print today's morning brief
python3 bot/send_brief.py --mode evening --dry-run --date 2026-11-07
python3 -m http.server 8000                                 # then open http://localhost:8000
```

There is no test suite. For a change to the web app, check it at phone width
(360–390px) and desktop, light and dark mode, with no horizontal scroll and no
console errors (Playwright headless works well for this). For a bot change,
dry-run several dates and keep each message under Telegram's 4096 characters;
messages use Telegram's HTML mode, so only `<b> <i> <code> <a>` and every tag
must close on its own line.

## Telegram bot

- Bot: `@milan_crowd_radar_bot`, created with @BotFather by the owner.
- Secrets (GitHub → Settings → Secrets and variables → Actions):
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (comma-separated ids). Optional
  repository variable `DASHBOARD_URL` overrides the link at the bottom of messages
  (defaults to the web app).
- Manual runs (Actions → Telegram brief → Run workflow, or
  `gh workflow run telegram-brief.yml -f mode=<mode>`): `morning`, `evening`,
  `dry-run`, `find-chat-id`.
- Every failure and the chat ids found by `find-chat-id` are written as GitHub
  **annotations**, so read them on the run page (or
  `gh api repos/davidev886/milan-crowd-radar/check-runs/<job id>/annotations`)
  rather than digging in logs.
- **Summer/winter time:** GitHub cron is UTC-only, so each send is scheduled
  twice (05:07 + 06:07 UTC, 17:07 + 18:07 UTC) and the script only sends from the
  entry that lands on the right Milan hour (`--target-local-hour`,
  `--scheduled-utc-hour`). Change both together.
- **Adding a recipient:** they open `t.me/milan_crowd_radar_bot` and tap Start;
  within 24 h (Telegram's `getUpdates` window) run `find-chat-id`; the owner
  appends the id to `TELEGRAM_CHAT_ID`. Ids already stored as secrets show as `***`.
- A bot can only message people who started it; strangers who tap Start get
  nothing unless their id is added.

## Outside this repo

- **Cloud routine** "Milan crowd radar – morning refresh", daily 06:40
  Europe/Rome, runs unattended in the owner's claude.ai account. Its prompt
  holds the research steps, the private dashboard link, and the push to this
  repo (it only touches `data/events.json` and `data/briefing.json`). Manage it
  from the CLI with `/schedule list`, `/schedule update`, `/schedule run`, or at
  claude.ai/code/routines. It reads yesterday's data from the dashboard, not
  from this repo.
- **GitHub Pages**: Settings → Pages → Deploy from a branch → `main` / root.
- **GitHub Actions minutes**: free and unlimited because the repo is public.

## Conventions

- No dependencies and no build step, for both the bot and the web app.
- In `index.html`, data goes into the page with `textContent` only (via the
  `h()` helper), never `innerHTML`; links are allowed only if they start with `https://`.
- Pressure colours are one blue ramp, validated for contrast. It runs
  light→dark in light mode and dark→light in dark mode, so wording on the page
  must not say "darker = more". Pressure is always shown with its number and
  label too, never colour alone.
- Times are Milan time everywhere. Compute "today" in `Europe/Rome`, not UTC.
- Wording on the page and in messages: plain English, short; impact scores are
  presented as estimates.

## Known limitations and ideas

- The routine treats its private dashboard as the source of truth, so edits
  made here to `data/` are lost the next morning. Possible fix: make the routine
  read `data/*.json` from this repo instead.
- GitHub can start scheduled runs a few minutes late.
- The "ubuntu-latest will migrate to Ubuntu 26" notice on runs is harmless (the
  workflow uses the runner's own `python3`).
- Ideas the owner may ask for: Italian version of the page and messages, a
  calendar (.ics) feed, filtering by zone, a custom domain for the site.
