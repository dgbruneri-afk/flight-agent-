"""Amadeus Flight Offers Search wrapper + query permutation builder.

Returns a list of `Quote` dicts shaped like:
  {
    "route_id": "MXP-ANC-direct-2026-08-06-2026-08-20",
    "kind": "direct" | "open_jaw" | "stopover",
    "legs": [{"from": "MXP", "to": "ANC", "date": "2026-08-06"}, ...],
    "price": 1234.56,
    "currency": "EUR",
    "carriers": ["LH", "AS"],
    "deeplink": "https://www.google.com/travel/flights?q=...",
  }
"""
from __future__ import annotations

import itertools
import os
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from amadeus import Client, ResponseError


@dataclass
class Leg:
    origin: str
    destination: str
    date: str  # YYYY-MM-DD


def _client() -> Client:
    return Client(
        client_id=os.environ["AMADEUS_API_KEY"],
        client_secret=os.environ["AMADEUS_API_SECRET"],
        hostname=os.environ.get("AMADEUS_HOSTNAME", "production"),
    )


def _date_range(target: str | date, flex: int) -> list[str]:
    d = target if isinstance(target, date) else date.fromisoformat(target)
    return [(d + timedelta(days=i)).isoformat() for i in range(-flex, flex + 1)]


def _google_flights_link(legs: list[Leg]) -> str:
    parts = ["Flights"]
    for i, leg in enumerate(legs):
        connector = "from" if i == 0 else "then"
        parts += [connector, leg.origin, "to", leg.destination, "on", leg.date]
    return "https://www.google.com/travel/flights?q=" + "+".join(parts)


def build_permutations(cfg: dict) -> list[dict]:
    """Build the full search grid as a list of query specs."""
    outs = _date_range(cfg["outbound_target"], cfg["date_flex_days"])
    rets = _date_range(cfg["return_target"], cfg["date_flex_days"])
    queries: list[dict] = []

    for origin in cfg["origins"]:
        for out_date, ret_date in itertools.product(outs, rets):
            if cfg.get("include_direct_roundtrip", True):
                for dest in cfg["destinations"]:
                    queries.append({
                        "kind": "direct",
                        "legs": [
                            Leg(origin, dest, out_date),
                            Leg(dest, origin, ret_date),
                        ],
                    })

            if cfg.get("include_open_jaw", True) and len(cfg["destinations"]) >= 2:
                a, b = cfg["destinations"][0], cfg["destinations"][1]
                queries.append({
                    "kind": "open_jaw",
                    "legs": [
                        Leg(origin, a, out_date),
                        Leg(b, origin, ret_date),
                    ],
                })
                queries.append({
                    "kind": "open_jaw",
                    "legs": [
                        Leg(origin, b, out_date),
                        Leg(a, origin, ret_date),
                    ],
                })

            if cfg.get("include_stopover_multicity", True):
                # Pick ONE hub per (origin, date) combo, rotating by hash —
                # keeps API budget down while still covering all hubs over time.
                hubs = cfg.get("stopover_hubs", [])
                if hubs:
                    hub = hubs[hash((origin, out_date, ret_date)) % len(hubs)]
                    primary_dest = cfg["destinations"][0]
                    queries.append({
                        "kind": "stopover",
                        "hub": hub,
                        "legs": [
                            Leg(origin, hub, out_date),
                            Leg(hub, primary_dest, out_date),
                            Leg(primary_dest, origin, ret_date),
                        ],
                    })

    return queries


def _route_id(q: dict) -> str:
    parts = [q["kind"]]
    for leg in q["legs"]:
        parts.append(f"{leg.origin}-{leg.destination}-{leg.date}")
    return ":".join(parts)


def search(cfg: dict, queries: Iterable[dict] | None = None) -> list[dict]:
    """Execute Amadeus searches for each query spec.

    Falls back gracefully on individual query errors so one bad query
    doesn't kill the whole run.
    """
    client = _client()
    queries = list(queries) if queries is not None else build_permutations(cfg)
    results: list[dict] = []

    for q in queries:
        try:
            body = _build_amadeus_body(q, cfg)
            resp = client.shopping.flight_offers_search.post(body)
            offers = resp.data or []
        except ResponseError as e:
            print(f"[warn] {_route_id(q)}: {e}")
            continue

        if not offers:
            continue

        # Sort by total price, keep top N
        offers.sort(key=lambda o: float(o["price"]["total"]))
        for o in offers[: cfg.get("max_results_per_query", 3)]:
            results.append({
                "route_id": _route_id(q),
                "kind": q["kind"],
                "legs": [vars(l) for l in q["legs"]],
                "price": float(o["price"]["total"]),
                "currency": o["price"].get("currency", cfg.get("currency", "EUR")),
                "carriers": sorted({
                    seg["carrierCode"]
                    for itin in o["itineraries"]
                    for seg in itin["segments"]
                }),
                "deeplink": _google_flights_link(q["legs"]),
            })

        # Be polite — Amadeus has a per-second rate limit on the free tier
        time.sleep(0.15)

    return results


def _build_amadeus_body(q: dict, cfg: dict) -> dict:
    """Translate our internal query spec into an Amadeus POST body."""
    origin_destinations = []
    for i, leg in enumerate(q["legs"], start=1):
        origin_destinations.append({
            "id": str(i),
            "originLocationCode": leg.origin,
            "destinationLocationCode": leg.destination,
            "departureDateTimeRange": {"date": leg.date},
        })

    return {
        "currencyCode": cfg.get("currency", "EUR"),
        "originDestinations": origin_destinations,
        "travelers": [
            {"id": str(i + 1), "travelerType": "ADULT"}
            for i in range(cfg.get("adults", 1))
        ],
        "sources": ["GDS"],
        "searchCriteria": {
            "maxFlightOffers": cfg.get("max_results_per_query", 3),
            "flightFilters": {
                "cabinRestrictions": [{
                    "cabin": cfg.get("travel_class", "ECONOMY"),
                    "coverage": "MOST_SEGMENTS",
                    "originDestinationIds": [str(i + 1) for i in range(len(q["legs"]))],
                }],
                **({"connectionRestriction": {"maxNumberOfConnections": 0}}
                   if cfg.get("nonstop_only") else {}),
            },
        },
    }
