"""Entry point — run the full check-and-alert pipeline once."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from . import diff, notify, search


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yml")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip Telegram send, print alerts to stdout instead.",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="First-time run: store baseline without sending alerts.",
    )
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    state_path = cfg["state_path"]

    print(f"[info] building search grid…")
    queries = search.build_permutations(cfg)
    print(f"[info] {len(queries)} queries to run")

    results = search.search(cfg, queries)
    print(f"[info] {len(results)} priced offers returned")

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
