from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from smartcity_iot.server_oa_v2 import run_server  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the smart community OA dashboard.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--households", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--tick-seconds", type=float, default=1.2)
    args = parser.parse_args()
    run_server(
        host=args.host,
        port=args.port,
        household_count=args.households,
        seed=args.seed,
        tick_seconds=args.tick_seconds,
    )


if __name__ == "__main__":
    main()
