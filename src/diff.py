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
    snapshot = {
        r["route_id"]: {
            "price": r["price"],
            "currency": r["currency"],
            "segment": r["segment"],
        }
        for r in current
    }
    p.write_text(json.dumps(snapshot, indent=2, sort_keys=True))


def compute_alerts(current: list[dict], previous: dict, cfg: dict) -> list[dict]:
    """Return alert dicts.

    Alert kinds:
      - 'price_drop'      : a tracked option (or TRIP_TOTAL) dropped >= alert_drop_pct
      - 'cheaper_option'  : a newly-seen date option is >= alert_new_route_pct
                            cheaper than the prior cheapest option in its segment
    """
    drop_threshold = cfg.get("alert_drop_pct", 10) / 100.0
    new_threshold = cfg.get("alert_new_route_pct", 15) / 100.0

    alerts: list[dict] = []

    # Price drops on known routes (includes TRIP_TOTAL)
    for r in current:
        prev = previous.get(r["route_id"])
        if not prev or prev["price"] <= 0:
            continue
        change = (r["price"] - prev["price"]) / prev["price"]
        if change <= -drop_threshold:
            alerts.append({
                "type": "price_drop",
                "route": r,
                "previous_price": prev["price"],
                "change_pct": round(change * 100, 1),
            })

    # New date option that beats the prior cheapest within the same segment
    prev_by_segment: dict[str, list[float]] = {}
    for v in previous.values():
        prev_by_segment.setdefault(v.get("segment"), []).append(v["price"])

    for r in current:
        if r["route_id"] in previous or r["segment"] == "TRIP_TOTAL":
            continue
        seg_prices = prev_by_segment.get(r["segment"])
        if not seg_prices:
            continue
        baseline = min(seg_prices)
        if r["price"] <= baseline * (1 - new_threshold):
            alerts.append({
                "type": "cheaper_option",
                "route": r,
                "baseline_price": baseline,
                "change_pct": round((r["price"] - baseline) / baseline * 100, 1),
            })

    return alerts
