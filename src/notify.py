"""Format and send alerts to Telegram."""
from __future__ import annotations

import os

import requests


def _dates(r: dict) -> str:
    if r.get("return"):
        return f"out {r['outbound']} / back {r['return']}"
    return f"{r['outbound']} one-way"


def _route_line(r: dict) -> str:
    if r["segment"] == "TRIP_TOTAL":
        lines = [f"<b>{r['price']:.0f} {r['currency']}</b> — {r['segment_label']}"]
        for b in r.get("breakdown", []):
            carriers = ", ".join(b["carriers"]) or "—"
            lines.append(
                f"  • {b['segment_label']}: {b['price']:.0f} {r['currency']} "
                f"({b['outbound']}→{b['return']}, {carriers})"
            )
        return "\n".join(lines)

    carriers = ", ".join(r["carriers"]) or "—"
    return (
        f"<b>{r['price']:.0f} {r['currency']}</b> · {r['segment_label']}\n"
        f"  {_dates(r)} · {carriers}\n"
        f"  <a href=\"{r['deeplink']}\">view on Google Flights</a>"
    )


def format_alerts(alerts: list[dict]) -> str:
    if not alerts:
        return ""

    drops = [a for a in alerts if a["type"] == "price_drop"]
    new = [a for a in alerts if a["type"] == "cheaper_option"]

    chunks = ["✈️ <b>Flight monitor</b>"]

    if drops:
        chunks.append(f"\n🔻 <b>Price drops</b> ({len(drops)})")
        for a in sorted(drops, key=lambda x: x["change_pct"]):
            chunks.append(
                f"{_route_line(a['route'])}\n"
                f"  was {a['previous_price']:.0f} → now {a['route']['price']:.0f} "
                f"({a['change_pct']:+.1f}%)"
            )

    if new:
        chunks.append(f"\n✨ <b>Cheaper date options</b> ({len(new)})")
        for a in sorted(new, key=lambda x: x["route"]["price"]):
            chunks.append(
                f"{_route_line(a['route'])}\n"
                f"  vs prior cheapest {a['baseline_price']:.0f} "
                f"({a['change_pct']:+.1f}%)"
            )

    return "\n\n".join(chunks)


def send(message: str) -> None:
    if not message:
        return
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    resp.raise_for_status()
