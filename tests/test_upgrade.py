from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coldchain_iot.config import SimulationConfig  # noqa: E402
from coldchain_iot.fleet import build_fleet  # noqa: E402
from coldchain_iot.orchestrator import run_simulation  # noqa: E402


class UpgradeTests(unittest.TestCase):
    def test_build_fleet(self) -> None:
        profiles, devices = build_fleet(device_count=6, route_count=3, seed=7)
        self.assertEqual(len(profiles), 6)
        self.assertEqual(len(devices), 6)
        self.assertEqual(len({profile.route_id for profile in profiles}), 3)

    def test_simulation_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = run_simulation(
                tmpdir,
                config=SimulationConfig(device_count=4, steps_per_device=24, route_count=2, seed=11),
            )
            self.assertEqual(summary["simulation"]["device_count"], 4)
            self.assertEqual(summary["simulation"]["record_count"], 96)
            self.assertIn("fleet_health_index", summary["batch"])
            self.assertTrue(summary["timeline"])
            self.assertTrue(summary["top_risk_events"])


if __name__ == "__main__":
    unittest.main()

