from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smartcity_iot.hub import CommunityHub  # noqa: E402


class SmartCityTests(unittest.TestCase):
    def test_snapshot_shape(self) -> None:
        hub = CommunityHub(household_count=8, seed=11, tick_seconds=0.1)
        for _ in range(16):
            hub.tick()
        snapshot = hub.snapshot()
        self.assertEqual(snapshot["kpis"]["household_count"], 8)
        self.assertEqual(len(snapshot["units"]), 8)
        self.assertTrue(snapshot["trend"])
        self.assertIn("work_orders", snapshot)
        self.assertIn("alerts", snapshot)

    def test_order_actions(self) -> None:
        hub = CommunityHub(household_count=10, seed=3, tick_seconds=0.1)
        for _ in range(24):
            hub.tick()
        snapshot = hub.snapshot()
        self.assertTrue(snapshot["work_orders"], "Expected work orders after several ticks")
        order = snapshot["work_orders"][0]
        status = order["status"]
        if status == "new":
            action = "assign"
        elif status == "assigned":
            action = "start"
        elif status == "processing":
            action = "resolve"
        elif status == "resolved":
            action = "close"
        else:
            action = "reopen"
        ok, _, payload = hub.apply_order_action(order_id=order["order_id"], action=action, actor="test", note="unit test")
        self.assertTrue(ok)
        self.assertIsNotNone(payload)
        self.assertNotEqual(payload["status"], status)


if __name__ == "__main__":
    unittest.main()

