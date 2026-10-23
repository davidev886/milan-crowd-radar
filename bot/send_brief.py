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
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TZ = ZoneInfo("Europe/Rome")
LABELS = ["Quiet", "Low", "Moderate", "Busy", "High", "Extreme"]
MAX_LEN = 4000  # Telegram allows 4096 characters per message
DEFAULT_DASHBOARD = "https://claude.ai/artifact/K9ot1C95hQFX1uB4xEN5dk"


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


def pressure(on: list[dict]) -> int:
    """Highest taxi or Linate impact of the day's events, +1 when three or more overlap (max 5).

    Same rule as the dashboard's pressure calendar.
    """
    if not on:
        return 0
    top = max(max(int(e.get("taxi", 0)), int(e.get("linate", 0))) for e in on)
    return min(5, top + (1 if len(on) >= 3 else 0))


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
    return [f'\n<a href="{html.escape(dashboard, quote=True)}">Open the dashboard</a>'] if dashboard else []


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


def find_chat_ids(token: str) -> int:
    res = api(token, "getUpdates")
    if not res.get("ok"):
        print(f"Telegram error: {res.get('description')}", file=sys.stderr)
        return 1
    chats = {}
    for upd in res.get("result", []):
        for key in ("message", "channel_post", "my_chat_member", "edited_message"):
            msg = upd.get(key)
            if msg and msg.get("chat"):
                c = msg["chat"]
                chats[c["id"]] = c.get("title") or c.get("username") or c.get("first_name") or c.get("type")
    if not chats:
        print("No chats found. Open your bot in Telegram, press Start (or send it any message), then run this again.")
        return 1
    print("Chats that have messaged the bot (use the id as TELEGRAM_CHAT_ID):")
    for cid, name in chats.items():
        print(f"  {cid}  {name}")
    return 0


def send(token: str, chat_ids: list[str], text: str) -> int:
    failures = 0
    for cid in chat_ids:
        res = api(token, "sendMessage", {
            "chat_id": cid,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        })
        if res.get("ok"):
            print(f"Sent to chat {cid}.")
        else:
            failures += 1
            print(f"Could not send to chat {cid}: {res.get('description')}", file=sys.stderr)
    return 1 if failures else 0


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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["morning", "evening", "find-chat-id"], default="morning")
    p.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
    p.add_argument("--date", help="pretend today is YYYY-MM-DD (Milan time)")
    p.add_argument("--target-local-hour", type=int, help="only send if the scheduled run lands on this hour in Milan")
    p.add_argument("--scheduled-utc-hour", type=int, help="the UTC hour of the cron entry that started this run")
    args = p.parse_args(argv)

    now = dt.datetime.now(dt.timezone.utc)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

    if args.mode == "find-chat-id":
        if not token:
            print("Set the TELEGRAM_BOT_TOKEN secret first.", file=sys.stderr)
            return 1
        return find_chat_ids(token)

    if not should_run(args.target_local_hour, args.scheduled_utc_hour, now):
        print("Not this run's hour in Milan (summer/winter time); skipping.")
        return 0

    today = dt.date.fromisoformat(args.date) if args.date else now.astimezone(TZ).date()
    events = load_json("events.json")
    briefing = {b.get("date"): b for b in load_json("briefing.json") if b.get("date")}
    dashboard = os.environ.get("DASHBOARD_URL", DEFAULT_DASHBOARD).strip()

    build = build_morning if args.mode == "morning" else build_evening
    text = fit(build(today, events, briefing, dashboard))

    if args.dry_run:
        print(text)
        print(f"\n[{len(text)} characters]")
        return 0

    chat_ids = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set. Add it as a repository secret.", file=sys.stderr)
        return 1
    if not chat_ids:
        print("TELEGRAM_CHAT_ID is not set. Run the workflow in 'find-chat-id' mode to get it.", file=sys.stderr)
        return 1
    return send(token, chat_ids, text)


if __name__ == "__main__":
    sys.exit(main())
