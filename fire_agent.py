#!/usr/bin/env python3
"""
Background fire-monitoring agent.

Polls the CAL FIRE public GeoJSON feed on a schedule and sends Teams alerts
for new incidents in your configured counties (see MONITOR_COUNTIES in .env).

Usage:
  python3 fire_agent.py              # run until Ctrl+C
  python3 fire_agent.py --once       # single check, then exit
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from fire_check import check_fires, send_test_alert  # noqa: E402


def interval_seconds() -> int:
    minutes = float(os.getenv("CHECK_INTERVAL_MINUTES", "5"))
    if minutes <= 0:
        raise ValueError("CHECK_INTERVAL_MINUTES must be greater than 0")
    return int(minutes * 60)


def run_loop(once: bool) -> int:
    stop = False

    def handle_signal(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    wait = interval_seconds()
    print(f"Fire agent started. Checking every {wait // 60} minute(s). Ctrl+C to stop.")

    while True:
        started = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"\n--- Check at {started} ---")
        try:
            check_fires()
        except Exception as exc:
            print(f"ERROR during check: {exc}", file=sys.stderr)

        if once or stop:
            print("Fire agent stopped.")
            return 0

        print(f"Next check in {wait // 60} minute(s)...")
        for _ in range(wait):
            if stop:
                print("Fire agent stopped.")
                return 0
            time.sleep(1)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CAL FIRE monitoring agent (scheduled checks + Teams alerts)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one check and exit (same as: python3 fire_check.py)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send one test alert and exit",
    )
    parser.add_argument(
        "--test-teams",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if args.test or args.test_teams:
        send_test_alert()
        return 0

    return run_loop(once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
