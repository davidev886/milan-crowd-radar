# Milan crowd radar — Telegram bot

Sends you a Telegram message every day about the events in Milan that bring in
crowds from outside and put pressure on taxis and Linate airport: trade fairs,
congresses, San Siro matches, big concerts, transport strikes and holidays.

- **07:07 Milan time** — today's brief: pressure score (0–5), where and when taxi
  demand peaks, Linate notes, weather, today's events, tomorrow, and the next 7 days.
- **19:07 Milan time** — a preview of tomorrow.

## How it works

```
Claude's scheduled task (06:40)          GitHub Actions (07:07 / 19:07)
  researches events & strikes   ──push──▶  data/events.json      ──▶ bot/send_brief.py ──▶ Telegram
  writes the daily brief                   data/briefing.json
  updates the dashboard
```

The pressure score is the highest taxi or Linate impact among the day's events,
plus one when three or more overlap (max 5) — the same rule as the dashboard.

## Setup (about 5 minutes)

1. **Create the bot.** In Telegram, open **@BotFather**, send `/newbot`, pick a
   name and a username. BotFather replies with a token like `123456:ABC-…`.
   Keep it private.
2. **Say hello to your bot.** Open the link BotFather gives you and press
   **Start**. (For a group: add the bot to the group and send a message there.)
3. **Store the token in this repo.** On GitHub: **Settings → Secrets and
   variables → Actions → New repository secret**. Name `TELEGRAM_BOT_TOKEN`,
   value the token.
4. **Find your chat id.** **Actions → Telegram brief → Run workflow**, choose
   `find-chat-id`, run it, open the run's log and copy the number shown.
5. **Store the chat id.** Add a second secret, `TELEGRAM_CHAT_ID`, with that
   number. Several chats: separate the ids with commas.
6. **Test it.** Run the workflow again with `morning`. The message should
   arrive within a minute.

After that it runs by itself.

## Handy things

- **Preview without sending:** run the workflow with `dry-run`, or locally:
  `python3 bot/send_brief.py --dry-run` (`--mode evening`, `--date 2026-11-08`).
- **Change the times:** edit the `cron` lines in
  `.github/workflows/telegram-brief.yml` and the matching
  `--target-local-hour` / `--scheduled-utc-hour` values. Each time is listed
  twice (summer and winter time) so it stays at the same Milan hour all year.
- **Drop the evening preview:** delete the two `17`/`18` cron lines.
- **Dashboard link:** set a repository variable `DASHBOARD_URL` to change it.
- **Data format:** `data/events.json` is a list of events with `start`/`end`
  dates, `taxi` and `linate` impact (1–5), times, venue, peak window and a tip;
  `data/briefing.json` has one written note per day. Claude's morning task
  rewrites both; you can also edit them by hand.

No packages to install: the script uses only the Python standard library.
