"""Entry point — run the full check-and-alert pipeline once."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from . import diff, notify, search


def _print_summary(results: list[dict]) -> None:
    for r in sorted(results, key=lambda x: (x["segment"] != "TRIP_TOTAL", x["segment"], x["price"])):
        if r["segment"] == "TRIP_TOTAL":
            print(f"  TRIP TOTAL: {r['price']:.0f} {r['currency']}")
            for b in r.get("breakdown", []):
                print(f"     - {b['segment_label']}: {b['price']:.0f} ({b['outbound']}→{b['return']})")
        else:
            print(f"  {r['price']:.0f} {r['currency']}  {r['segment_label']}  {r['outbound']}→{r['return']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yml")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip Telegram send; print alerts to stdout.")
    parser.add_argument("--seed", action="store_true",
                        help="First-time run: store baseline without sending alerts.")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    state_path = cfg["state_path"]

    print("[info] searching…")
    results = search.run_search(cfg)
    print(f"[info] {len(results)} priced results:")
    _print_summary(results)

    previous = diff.load_state(state_path)

    if args.seed or not previous:
        diff.save_state(state_path, results)
        print("[info] baseline seeded. No alerts sent.")
        return 0

    alerts = diff.compute_alerts(results, previous, cfg)
    print(f"[info] {len(alerts)} alerts")

    message = notify.format_alerts(alerts)
    if args.dry_run:
        print("---")
        print(message or "(no alerts)")
    elif message:
        notify.send(message)
        print("[info] telegram sent")

    diff.save_state(state_path, results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
