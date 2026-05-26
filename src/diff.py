"""Compare current search results against last-seen state, decide on alerts."""
from __future__ import annotations

import json
from pathlib import Path


def load_state(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text() or "{}")


def save_state(path: str, current: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {r["route_id"]: {"price": r["price"], "currency": r["currency"]}
                for r in current}
    p.write_text(json.dumps(snapshot, indent=2, sort_keys=True))


def compute_alerts(current: list[dict], previous: dict, cfg: dict) -> list[dict]:
    """Return a list of alert dicts describing what changed.

    Alert kinds:
      - 'price_drop'   : known route dropped >= alert_drop_pct
      - 'cheaper_route': newly-seen route is >= alert_new_route_pct cheaper
                         than the current cheapest known route
    """
    drop_threshold = cfg.get("alert_drop_pct", 10) / 100.0
    new_threshold = cfg.get("alert_new_route_pct", 15) / 100.0

    alerts: list[dict] = []

    # Known-route price drops
    for r in current:
        prev = previous.get(r["route_id"])
        if not prev:
            continue
        prev_price = prev["price"]
        if prev_price <= 0:
            continue
        change = (r["price"] - prev_price) / prev_price
        if change <= -drop_threshold:
            alerts.append({
                "type": "price_drop",
                "route": r,
                "previous_price": prev_price,
                "change_pct": round(change * 100, 1),
            })

    # New routes that beat the current cheapest known route
    if previous:
        current_cheapest = min((v["price"] for v in previous.values()), default=None)
        if current_cheapest:
            for r in current:
                if r["route_id"] in previous:
                    continue
                if r["price"] <= current_cheapest * (1 - new_threshold):
                    alerts.append({
                        "type": "cheaper_route",
                        "route": r,
                        "baseline_price": current_cheapest,
                        "change_pct": round(
                            (r["price"] - current_cheapest) / current_cheapest * 100, 1
                        ),
                    })

    return alerts
