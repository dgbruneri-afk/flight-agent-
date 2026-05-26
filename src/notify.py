"""Format and send alerts to Telegram."""
from __future__ import annotations

import os

import requests


def _format_route_line(r: dict) -> str:
    legs = r["legs"]
    path = " → ".join([legs[0]["origin"]] + [l["destination"] for l in legs])
    dates = " / ".join(l["date"] for l in legs)
    carriers = ", ".join(r["carriers"])
    return (f"<b>{r['price']:.0f} {r['currency']}</b> · {path}\n"
            f"  {dates} · {carriers} · <i>{r['kind']}</i>\n"
            f"  <a href=\"{r['deeplink']}\">view on Google Flights</a>")


def format_alerts(alerts: list[dict]) -> str:
    if not alerts:
        return ""

    drops = [a for a in alerts if a["type"] == "price_drop"]
    new = [a for a in alerts if a["type"] == "cheaper_route"]

    chunks = ["✈️ <b>Flight monitor</b>"]

    if drops:
        chunks.append(f"\n🔻 <b>Price drops</b> ({len(drops)})")
        for a in sorted(drops, key=lambda x: x["change_pct"]):
            chunks.append(
                f"{_format_route_line(a['route'])}\n"
                f"  was {a['previous_price']:.0f} → now {a['route']['price']:.0f} "
                f"({a['change_pct']:+.1f}%)"
            )

    if new:
        chunks.append(f"\n✨ <b>New cheaper routes</b> ({len(new)})")
        for a in sorted(new, key=lambda x: x["route"]["price"]):
            chunks.append(
                f"{_format_route_line(a['route'])}\n"
                f"  vs current cheapest {a['baseline_price']:.0f} "
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
