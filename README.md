# Milan crowd radar

Day by day: the events in Milan that bring in crowds from outside and put
pressure on taxis and Linate airport — trade fairs, congresses, San Siro
matches, big concerts, transport strikes and holidays.

**Web app:** https://davidev886.github.io/milan-crowd-radar/ — today's pressure,
the next 7 days, a pressure calendar and a searchable list of every event. On a
phone, Share → Add to Home Screen to open it like an app.

**Telegram bot:** a message every day —

- **07:07 Milan time** — today's brief: pressure score (0–5), where and when taxi
  demand peaks, Linate notes, weather, today's events, tomorrow, and the next 7 days.
- **19:07 Milan time** — a preview of tomorrow.

## How it works

```
Claude's scheduled task (06:40)          this repo                    readers
  researches events & strikes   ──push──▶  data/events.json   ──▶ index.html on GitHub Pages
  writes the daily brief                   data/briefing.json ──▶ bot/send_brief.py ──▶ Telegram (07:07 / 19:07)
```

Each push of new data redeploys the web app automatically. The pressure score
is the highest taxi or Linate impact among the day's events, plus one when three
or more overlap (max 5). Impact scores are estimates; dates come from the
sources linked on each event.

## Telegram setup (about 5 minutes)

1. **Create the bot.** In Telegram, open **@BotFather**, send `/newbot`, pick a
   name and a username. BotFather replies with a token like `123456:ABC-…`.
   Keep it private.
2. **Say hello to your bot.** Open the link BotFather gives you and press
   **Start**. (For a group: add the bot to the group and send a message there.)
3. **Store the token in this repo.** On GitHub: **Settings → Secrets and
   variables → Actions → New repository secret**. Name `TELEGRAM_BOT_TOKEN`,
   value the token.
4. **Find your chat id.** **Actions → Telegram brief → Run workflow**, choose
   `find-chat-id` and run it. The number appears under **Annotations** on the
   run's page ("Your chat id").
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
- **Add someone:** they open `t.me/<your bot>` and tap Start (within 24 h of
  the next step), run `find-chat-id`, then add their id to `TELEGRAM_CHAT_ID`
  after a comma.
- **Link in the messages:** points to the web app; set a repository variable
  `DASHBOARD_URL` to change it.
- **Web app locally:** `python3 -m http.server` in this folder, then open
  http://localhost:8000.
- **Data format:** `data/events.json` is a list of events with `start`/`end`
  dates, `taxi` and `linate` impact (1–5), times, venue, peak window and a tip;
  `data/briefing.json` has one written note per day. Claude's morning task
  rewrites both; you can also edit them by hand.

No packages to install: the script uses only the Python standard library.
