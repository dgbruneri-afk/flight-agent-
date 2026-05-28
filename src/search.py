"""SerpAPI Google Flights search + trip-total combination logic.

Each segment has one or more date options (outbound/return pairs). We price
every option, keep the cheapest per segment, and sum the cheapest of the
segments flagged `in_total` to get the trip total.

Returns a list of `Quote` dicts:
  {
    "route_id": "MXP-SFO:2026-08-05:2026-08-21",
    "segment": "MXP-SFO",
    "segment_label": "Milan <-> San Francisco",
    "departure": "MXP", "arrival": "SFO",
    "outbound": "2026-08-05", "return": "2026-08-21",
    "price": 812.0, "currency": "EUR",
    "carriers": ["LH", "UA"],
    "duration_min": 1180,
    "deeplink": "https://www.google.com/travel/flights?q=...",
  }
Plus one synthetic TRIP_TOTAL quote with a `breakdown` list.
"""
from __future__ import annotations

import os
import time
from datetime import date

import requests

SERPAPI_URL = "https://serpapi.com/search.json"


def _isodate(d: str | date | None) -> str | None:
    if d is None:
        return None
    return d.isoformat() if isinstance(d, date) else str(d)


def _google_flights_link(dep: str, arr: str, outbound: str, ret: str | None) -> str:
    parts = ["Flights", "from", dep, "to", arr, "on", outbound]
    if ret:
        parts += ["returning", ret]
    else:
        parts += ["one", "way"]
    return "https://www.google.com/travel/flights?q=" + "+".join(parts)


def _search_one(dep: str, arr: str, outbound: str, ret: str | None, cfg: dict) -> dict:
    params = {
        "engine": "google_flights",
        "departure_id": dep,
        "arrival_id": arr,
        "outbound_date": outbound,
        "currency": cfg.get("currency", "EUR"),
        "hl": "en",
        "adults": cfg.get("adults", 1),
        "travel_class": cfg.get("travel_class", 1),
        "api_key": os.environ["SERPAPI_KEY"],
    }
    if ret:
        params["return_date"] = ret
        params["type"] = 1  # round trip
    else:
        params["type"] = 2  # one way
    resp = requests.get(SERPAPI_URL, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _cheapest_offer(data: dict) -> dict | None:
    options = (data.get("best_flights") or []) + (data.get("other_flights") or [])
    priced = [o for o in options if o.get("price") is not None]
    if not priced:
        return None
    best = min(priced, key=lambda o: o["price"])
    carriers = sorted({
        seg.get("airline")
        for seg in best.get("flights", [])
        if seg.get("airline")
    })
    return {
        "price": float(best["price"]),
        "carriers": carriers,
        "duration_min": best.get("total_duration"),
    }


def run_search(cfg: dict) -> list[dict]:
    results: list[dict] = []

    for seg in cfg["segments"]:
        for opt in seg["date_options"]:
            outbound = _isodate(opt["outbound"])
            ret = _isodate(opt.get("return"))
            try:
                data = _search_one(seg["departure"], seg["arrival"], outbound, ret, cfg)
            except requests.RequestException as e:
                print(f"[warn] {seg['id']} {outbound}/{ret}: {e}")
                continue

            if data.get("error"):
                print(f"[warn] {seg['id']} {outbound}/{ret}: {data['error']}")
                continue

            offer = _cheapest_offer(data)
            if not offer:
                print(f"[warn] {seg['id']} {outbound}/{ret}: no priced offers")
                continue

            results.append({
                "route_id": f"{seg['id']}:{outbound}:{ret or 'oneway'}",
                "segment": seg["id"],
                "segment_label": seg.get("label", seg["id"]),
                "departure": seg["departure"],
                "arrival": seg["arrival"],
                "outbound": outbound,
                "return": ret,
                "price": offer["price"],
                "currency": cfg.get("currency", "EUR"),
                "carriers": offer["carriers"],
                "duration_min": offer["duration_min"],
                "in_total": seg.get("in_total", True),
                "deeplink": _google_flights_link(seg["departure"], seg["arrival"], outbound, ret),
            })
            time.sleep(0.3)  # gentle on the API

    total_quote = _trip_total(cfg, results)
    if total_quote:
        results.append(total_quote)

    return results


def _trip_total(cfg: dict, results: list[dict]) -> dict | None:
    """Sum the cheapest priced option of each `in_total` segment."""
    total = 0.0
    breakdown = []
    for seg in cfg["segments"]:
        if not seg.get("in_total", True):
            continue
        seg_quotes = [r for r in results if r["segment"] == seg["id"]]
        if not seg_quotes:
            return None  # incomplete — can't compute a meaningful total
        cheapest = min(seg_quotes, key=lambda r: r["price"])
        total += cheapest["price"]
        breakdown.append({
            "segment_label": cheapest["segment_label"],
            "route_id": cheapest["route_id"],
            "price": cheapest["price"],
            "outbound": cheapest["outbound"],
            "return": cheapest["return"],
            "carriers": cheapest["carriers"],
            "deeplink": cheapest["deeplink"],
        })

    if not breakdown:
        return None

    return {
        "route_id": "TRIP_TOTAL",
        "segment": "TRIP_TOTAL",
        "segment_label": cfg.get("trip_name", "Trip total"),
        "price": round(total, 2),
        "currency": cfg.get("currency", "EUR"),
        "carriers": [],
        "breakdown": breakdown,
        "deeplink": None,
    }
