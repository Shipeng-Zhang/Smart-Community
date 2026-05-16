from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coldchain_iot.analytics import _score_device  # noqa: E402
from coldchain_iot.cloud import CloudPlatform  # noqa: E402
from coldchain_iot.device import ColdChainTruckDevice, DeviceProfile  # noqa: E402
from coldchain_iot.edge import EdgeGateway  # noqa: E402
from coldchain_iot.security import sign_envelope, verify_envelope  # noqa: E402


class SecurityTests(unittest.TestCase):
    def test_sign_and_verify(self) -> None:
        payload = {"device_id": "A", "sequence_id": 1}
        envelope = sign_envelope(payload, "secret", timestamp=1_700_000_000, nonce="abc")
        ok, reason = verify_envelope(envelope, "secret", now=1_700_000_001)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")


class EdgeTests(unittest.TestCase):
    def test_high_temperature_triggers_alert(self) -> None:
        profile = DeviceProfile(
            device_id="TRUCK-TEST",
            route_id="ROUTE-TEST",
            secret="demo-secret",
            base_temperature_c=3.0,
            base_humidity_pct=60.0,
            base_latitude=31.0,
            base_longitude=121.0,
            anomaly_mode="compressor_fault",
        )
        device = ColdChainTruckDevice(profile, seed=1)
        envelope = device.generate_envelope(28, datetime(2026, 5, 16, tzinfo=timezone.utc))
        gateway = EdgeGateway({profile.device_id: profile.secret})
        event = gateway.ingest(envelope)
        self.assertIn("冷链温度超阈值", event.alerts)
        self.assertGreaterEqual(event.edge_risk_score, 40.0)


class AnalyticsTests(unittest.TestCase):
    def test_device_scoring(self) -> None:
        sample_records = [
            {
                "packet": {"device_id": "A", "route_id": "R", "temperature_c": 4.0, "humidity_pct": 66.0},
                "edge_risk_score": 20.0,
                "processing_latency_ms": 20,
                "alerts": [],
            },
            {
                "packet": {"device_id": "A", "route_id": "R", "temperature_c": 9.0, "humidity_pct": 70.0},
                "edge_risk_score": 75.0,
                "processing_latency_ms": 26,
                "alerts": ["冷链温度超阈值"],
            },
        ]
        result = _score_device(sample_records)
        self.assertEqual(result["out_of_range_count"], 1)
        self.assertGreater(result["alert_count"], 0)
        self.assertLess(result["compliance_score"], 100.0)

    def test_cloud_final_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cloud = CloudPlatform(Path(tmpdir))
            record = {
                "device_id": "TRUCK-001",
                "route_id": "ROUTE-01",
                "sequence_id": 1,
                "collected_at": "2026-05-16T08:00:00+00:00",
                "temperature_c": 8.5,
                "humidity_pct": 72.0,
                "latitude": 31.0,
                "longitude": 121.0,
                "speed_kmh": 40.0,
                "door_open": False,
                "shock_g": 0.3,
                "battery_pct": 90.0,
            }
            envelope = sign_envelope(record, "x", timestamp=1_700_000_000, nonce="seed")
            gateway = EdgeGateway({"TRUCK-001": "x"})
            event = gateway.ingest(envelope)
            cloud.ingest(event)
            summary = cloud.finalize()
            self.assertEqual(summary["simulation"]["device_count"], 1)
            self.assertEqual(summary["simulation"]["record_count"], 1)


if __name__ == "__main__":
    unittest.main()
