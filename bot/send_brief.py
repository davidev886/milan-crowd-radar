#!/usr/bin/env python3
"""Milan crowd radar -> Telegram.

Builds a short brief of the events in Milan that put pressure on taxis and
Linate airport, from data/events.json and data/briefing.json, and sends it to
one or more Telegram chats.

Modes
  morning       today's brief, tomorrow, and the next 7 days at a glance
  evening       preview of tomorrow
  find-chat-id  list the chats that have messaged the bot (to get TELEGRAM_CHAT_ID)

Environment
  TELEGRAM_BOT_TOKEN  bot token from @BotFather (required to send)
  TELEGRAM_CHAT_ID    chat id(s), comma-separated (required to send)
  DASHBOARD_URL       optional link added at the bottom of each message

Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TZ = ZoneInfo("Europe/Rome")
LABELS = ["Quiet", "Low", "Moderate", "Busy", "High", "Extreme"]
MAX_LEN = 4000  # Telegram allows 4096 characters per message
DEFAULT_DASHBOARD = "https://davidev886.github.io/milan-crowd-radar/"


# ---------------------------------------------------------------- data

def load_json(name: str) -> list[dict]:
    path = DATA_DIR / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def events_on(events: list[dict], day: str) -> list[dict]:
    on = [e for e in events if e.get("start", "") <= day <= e.get("end", "")]
    return sorted(on, key=lambda e: max(int(e.get("taxi", 0)), int(e.get("linate", 0))), reverse=True)


def overlap(on: list[dict]) -> bool:
    """The +1: three events that each score 3+, or three in one zone ("City-wide" counts in every zone)."""
    if sum(max(int(e.get("taxi", 0)), int(e.get("linate", 0))) >= 3 for e in on) >= 3:
        return True
    city = sum(e.get("zone") == "City-wide" for e in on)
    zones = Counter(e.get("zone") for e in on if e.get("zone") != "City-wide")
    return city + max(zones.values(), default=0) >= 3


def pressure(on: list[dict]) -> int:
    """Highest taxi or Linate impact of the day's events, +1 per overlap() (max 5).

    Same rule as the web app's pressure calendar.
    """
    if not on:
        return 0
    top = max(max(int(e.get("taxi", 0)), int(e.get("linate", 0))) for e in on)
    return min(5, top + (1 if overlap(on) else 0))


# ---------------------------------------------------------------- formatting

def esc(s) -> str:
    return html.escape(str(s or ""), quote=False)


def fmt_day(d: dt.date) -> str:
    return f"{d:%a} {d.day} {d:%b}"


def dots(score: int) -> str:
    return "●" * score + "○" * (5 - score)


def short(name: str, n: int = 34) -> str:
    """Drop the bracketed part ("(Serie A)") and cap the length, for one-line lists."""
    base = name.split(" (")[0].strip() or name
    return base if len(base) <= n else base[: n - 1].rstrip() + "…"


def iso(d: dt.date) -> str:
    return d.isoformat()


def event_line(e: dict) -> str:
    time = e.get("time") or ""
    parts = [f"• <b>{esc(e.get('name'))}</b>"]
    where = " · ".join(x for x in (esc(time), esc(e.get("venue"))) if x)
    if where:
        parts.append(f"\n   {where}")
    parts.append(f"\n   Taxi {int(e.get('taxi', 0))}/5 · Linate {int(e.get('linate', 0))}/5")
    if e.get("peak"):
        parts.append(f" · peak {esc(e['peak'])}")
    if e.get("tip"):
        parts.append(f"\n   <i>{esc(e['tip'])}</i>")
    return "".join(parts)


def day_block(day: dt.date, events: list[dict], brief: dict | None, title: str, max_events: int = 6) -> list[str]:
    on = events_on(events, iso(day))
    score = pressure(on)
    out = [f"<b>{esc(title)} · {fmt_day(day)}</b>", f"Pressure <b>{score}/5 · {LABELS[score]}</b>  {dots(score)}"]
    if brief and brief.get("headline"):
        out.append(f"\n{esc(brief['headline'])}")
    elif not on:
        out.append("\nNo major events listed.")
    if brief:
        for icon, key, label in (("🚕", "taxi", "Taxi"), ("✈️", "linate", "Linate"), ("🌦", "weather", "Weather")):
            if brief.get(key):
                out.append(f"{icon} {label}: {esc(brief[key])}")
    if on:
        out.append("")
        out.extend(event_line(e) for e in on[:max_events])
        if len(on) > max_events:
            out.append(f"   …and {len(on) - max_events} more")
    return out


def week_block(start: dt.date, events: list[dict], days: int = 7) -> list[str]:
    out = ["<b>Next 7 days</b>"]
    busiest = None
    for i in range(days):
        d = start + dt.timedelta(days=i)
        on = events_on(events, iso(d))
        score = pressure(on)
        names = ", ".join(short(e.get("name", "")) for e in on[:2])
        if len(on) > 2:
            names += f" +{len(on) - 2}"
        out.append(f"<code>{fmt_day(d):<10}</code> {dots(score)} {esc(names) if names else '—'}")
        if score > 0 and (busiest is None or score > busiest[1]):
            busiest = (d, score, on)
    if busiest:
        d, score, on = busiest
        out.append(f"\nBusiest: <b>{fmt_day(d)}</b> ({score}/5) – {esc(on[0].get('name'))}")
    return out


def footer(dashboard: str) -> list[str]:
    return [f'\n<a href="{html.escape(dashboard, quote=True)}">Open the web app</a>'] if dashboard else []


def build_morning(today: dt.date, events: list[dict], briefing: dict[str, dict], dashboard: str) -> str:
    tomorrow = today + dt.timedelta(days=1)
    lines = ["🚦 <b>Milan crowd radar</b>"]
    if iso(today) not in briefing:
        lines.append("<i>Today's written brief wasn't refreshed; showing the event list only.</i>")
    lines.append("")
    lines += day_block(today, events, briefing.get(iso(today)), "Today")
    lines.append("")
    t_on = events_on(events, iso(tomorrow))
    t_score = pressure(t_on)
    t_brief = briefing.get(iso(tomorrow))
    t_head = (t_brief or {}).get("headline") or (", ".join(e.get("name", "") for e in t_on[:2]) or "No major events listed")
    lines.append(f"<b>Tomorrow · {fmt_day(tomorrow)}</b>: {t_score}/5 {LABELS[t_score]} – {esc(t_head)}")
    lines.append("")
    lines += week_block(tomorrow, events)
    lines += footer(dashboard)
    return "\n".join(lines)


def build_evening(today: dt.date, events: list[dict], briefing: dict[str, dict], dashboard: str) -> str:
    tomorrow = today + dt.timedelta(days=1)
    lines = ["🌙 <b>Milan crowd radar · tomorrow</b>", ""]
    lines += day_block(tomorrow, events, briefing.get(iso(tomorrow)), "Tomorrow", max_events=8)
    lines += footer(dashboard)
    return "\n".join(lines)


def fit(text: str) -> str:
    if len(text) <= MAX_LEN:
        return text
    # Every line opens and closes its own tags, so cutting at a line break keeps the HTML valid.
    cut = text[:MAX_LEN]
    cut = cut[: cut.rfind("\n")]
    return cut + "\n…"


# ---------------------------------------------------------------- telegram

def _gh_escape(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotate(level: str, title: str, msg: str) -> None:
    """On GitHub Actions, also show the message in the run's Annotations box,
    so nobody has to open the log to see what happened."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::{level} title={title}::{_gh_escape(msg)}", flush=True)


def fail(msg: str) -> int:
    print(msg, file=sys.stderr, flush=True)
    annotate("error", "Telegram brief", msg)
    return 1


def explain(description: str) -> str:
    d = (description or "").lower()
    if "unauthorized" in d or d.strip() == "not found":  # 401 wrong token, 404 malformed token
        return "Telegram rejected the bot token. Copy it again from @BotFather and update the TELEGRAM_BOT_TOKEN secret."
    if "chat not found" in d:
        return "Telegram doesn't know that chat. Check TELEGRAM_CHAT_ID, and make sure you pressed Start in your bot."
    if "blocked" in d:
        return "The bot is blocked in that chat. Unblock it in Telegram and press Start."
    if "kicked" in d or "not a member" in d:
        return "The bot isn't in that group any more. Add it back to the group."
    if "conflict" in d and "webhook" in d:
        return "This bot has a webhook set, so its messages can't be listed. Remove the webhook or send any message and set TELEGRAM_CHAT_ID by hand."
    if d.startswith("could not reach telegram"):
        return f"{description[:1].upper()}{description[1:]}. GitHub may be having a network problem; the next run will try again."
    return f"Telegram said: {description}"


def api(token: str, method: str, params: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    body = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            payload = json.load(e)
        except Exception:  # noqa: BLE001
            payload = {"ok": False, "description": f"HTTP {e.code}"}
        return payload
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "description": f"could not reach Telegram ({e})"}


def check_token(token: str) -> str | None:
    """Return a problem description, or None if the token looks right. Never prints the token."""
    if not token:
        return "TELEGRAM_BOT_TOKEN is not set. Add it under Settings → Secrets and variables → Actions (the name must be exactly TELEGRAM_BOT_TOKEN)."
    if not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{30,}", token):
        return ("TELEGRAM_BOT_TOKEN doesn't look like a bot token (it should be numbers, a colon, then a long code, "
                "with no quotes or spaces). Copy it again from @BotFather.")
    return None


def find_chat_ids(token: str) -> int:
    me = api(token, "getMe")
    if not me.get("ok"):
        return fail(explain(me.get("description")))
    bot = me["result"].get("username", "your bot")
    res = api(token, "getUpdates")
    if not res.get("ok"):
        return fail(explain(res.get("description")))
    chats = {}
    for upd in res.get("result", []):
        for key in ("message", "channel_post", "my_chat_member", "edited_message"):
            msg = upd.get(key)
            if msg and msg.get("chat"):
                c = msg["chat"]
                chats[c["id"]] = c.get("title") or c.get("username") or c.get("first_name") or c.get("type")
    if not chats:
        return fail(f"The token works (bot @{bot}), but nobody has messaged it yet. Open https://t.me/{bot} in Telegram, "
                    "press Start or send any message, then run find-chat-id again.")
    print(f"Chats that have messaged @{bot} (use the id as TELEGRAM_CHAT_ID):")
    for cid, name in chats.items():
        print(f"  {cid}  {name}")
        annotate("notice", "Your chat id", f"{cid} ({name}). Save this number as the TELEGRAM_CHAT_ID secret.")
    return 0


def send(token: str, chat_ids: list[str], text: str) -> int:
    sent, problems = 0, []
    for cid in chat_ids:
        res = api(token, "sendMessage", {
            "chat_id": cid,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        })
        if res.get("ok"):
            sent += 1
            print(f"Sent to chat {cid}.")
        else:
            problems.append(f"chat {cid}: {explain(res.get('description'))}")
    if sent:
        annotate("notice", "Telegram brief", f"Sent to {sent} chat(s).")
    if problems:
        return fail("Could not send to " + " | ".join(problems))
    return 0


# ---------------------------------------------------------------- main

def should_run(target_hour: int | None, scheduled_utc_hour: int | None, now: dt.datetime) -> bool:
    """GitHub cron is UTC-only. The workflow schedules each send twice (summer and
    winter time); only the run whose scheduled UTC hour equals the target local
    hour in Milan today goes ahead. Uses the scheduled hour, not the actual run
    time, so a delayed run never sends twice."""
    if target_hour is None or scheduled_utc_hour is None:
        return True
    local = now.astimezone(TZ)
    offset = int(local.utcoffset().total_seconds() // 3600)
    return (scheduled_utc_hour + offset) % 24 == target_hour


def refreshed_today(briefing: dict[str, dict], today: dt.date) -> bool:
    """briefing.json starts on the routine's run day, so this is True once today's refresh has landed."""
    return min(briefing, default="") == iso(today)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["morning", "evening", "find-chat-id"], default="morning")
    p.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
    p.add_argument("--date", help="pretend today is YYYY-MM-DD (Milan time)")
    p.add_argument("--target-local-hour", type=int, help="only send if the scheduled run lands on this hour in Milan")
    p.add_argument("--scheduled-utc-hour", type=int, help="the UTC hour of the cron entry that started this run")
    p.add_argument("--after-push", action="store_true",
                   help="started by a data push: send only if it is today's refresh and before 10:00 in Milan")
    p.add_argument("--unless-refreshed", action="store_true",
                   help="backup run: skip if today's refresh has landed (its push already sent the brief)")
    args = p.parse_args(argv)

    now = dt.datetime.now(dt.timezone.utc)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

    if token.lower().startswith("bot") and token[3:4].isdigit():
        token = token[3:]  # a pasted "bot123:ABC…" still works

    if args.mode == "find-chat-id":
        problem = check_token(token)
        if problem:
            return fail(problem)
        return find_chat_ids(token)

    if not should_run(args.target_local_hour, args.scheduled_utc_hour, now):
        print("Not this run's hour in Milan (summer/winter time); skipping.")
        return 0

    today = dt.date.fromisoformat(args.date) if args.date else now.astimezone(TZ).date()
    events = load_json("events.json")
    briefing = {b.get("date"): b for b in load_json("briefing.json") if b.get("date")}
    dashboard = os.environ.get("DASHBOARD_URL", DEFAULT_DASHBOARD).strip()

    # ponytail: no record of what was sent. If the routine pushes after a backup
    # run has already sent, that day gets two briefs; a sent-log would fix it.
    if args.after_push and not (refreshed_today(briefing, today) and now.astimezone(TZ).hour < 10):
        print("Not this morning's refresh (or past 10:00 in Milan); skipping.")
        return 0
    if args.unless_refreshed and refreshed_today(briefing, today):
        print("Today's refresh has landed and its push sent the brief; skipping.")
        return 0

    build =build_morning if args.mode == "morning" else build_evening
    text = fit(build(today, events, briefing, dashboard))

    if args.dry_run:
        print(text)
        print(f"\n[{len(text)} characters]")
        return 0

    chat_ids = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    problem = check_token(token)
    if problem:
        return fail(problem)
    if not chat_ids:
        return fail("TELEGRAM_CHAT_ID is not set. Run the workflow with 'find-chat-id' to get your chat id, "
                    "then save it as a secret named exactly TELEGRAM_CHAT_ID.")
    return send(token, chat_ids, text)


if __name__ == "__main__":
    sys.exit(main())
