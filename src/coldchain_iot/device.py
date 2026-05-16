from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from coldchain_iot.models import TelemetryPacket
from coldchain_iot.security import sign_envelope


@dataclass(slots=True)
class DeviceProfile:
    device_id: str
    route_id: str
    secret: str
    base_temperature_c: float
    base_humidity_pct: float
    base_latitude: float
    base_longitude: float
    anomaly_mode: str


class ColdChainTruckDevice:
    def __init__(self, profile: DeviceProfile, *, seed: int) -> None:
        self.profile = profile
        self.random = random.Random(seed)

    def _route_position(self, step: int) -> tuple[float, float]:
        lat = self.profile.base_latitude + 0.01 * math.sin(step / 7)
        lon = self.profile.base_longitude + 0.014 * math.cos(step / 9)
        return round(lat, 6), round(lon, 6)

    def _temperature(self, step: int) -> float:
        temp = self.profile.base_temperature_c + 0.4 * math.sin(step / 5)
        if self.profile.anomaly_mode == "compressor_fault" and 18 <= step <= 28:
            temp += 4.5 + 0.15 * (step - 18)
        if self.profile.anomaly_mode == "door_risk" and 20 <= step <= 24:
            temp += 2.2
        return round(temp, 2)

    def _humidity(self, step: int) -> float:
        humidity = self.profile.base_humidity_pct + 4.0 * math.cos(step / 6)
        if self.profile.anomaly_mode == "compressor_fault" and 18 <= step <= 28:
            humidity += 6.0
        return round(max(35.0, min(98.0, humidity)), 2)

    def _door_open(self, step: int) -> bool:
        return self.profile.anomaly_mode == "door_risk" and step in {22, 23}

    def _shock_g(self, step: int) -> float:
        base = 0.18 + abs(math.sin(step / 4)) * 0.12
        if self.profile.anomaly_mode == "rough_road" and step in {34, 35, 36}:
            base += 1.2
        if self.profile.anomaly_mode == "door_risk" and step == 22:
            base += 0.8
        return round(base, 2)

    def generate_envelope(self, step: int, base_time: datetime) -> dict[str, object]:
        lat, lon = self._route_position(step)
        temperature = self._temperature(step)
        humidity = self._humidity(step)
        speed = 46.0 + 8.0 * math.sin(step / 8)
        if self.profile.anomaly_mode == "door_risk" and self._door_open(step):
            speed -= 15.0
        packet = TelemetryPacket(
            device_id=self.profile.device_id,
            route_id=self.profile.route_id,
            sequence_id=step,
            collected_at=(base_time + timedelta(minutes=step)).astimezone(timezone.utc).isoformat(),
            temperature_c=temperature,
            humidity_pct=humidity,
            latitude=lat,
            longitude=lon,
            speed_kmh=round(max(5.0, speed), 2),
            door_open=self._door_open(step),
            shock_g=self._shock_g(step),
            battery_pct=round(98.0 - step * 0.22 + self.random.uniform(-0.2, 0.2), 2),
        )
        return sign_envelope(
            packet.to_dict(),
            self.profile.secret,
            timestamp=int((base_time + timedelta(minutes=step)).timestamp()),
            nonce=f"{self.profile.device_id}-{step:03d}",
        )


def default_profiles() -> list[DeviceProfile]:
    return [
        DeviceProfile(
            device_id="TRUCK-001",
            route_id="ROUTE-SH-HZ-01",
            secret="cold-chain-alpha",
            base_temperature_c=3.2,
            base_humidity_pct=68.0,
            base_latitude=31.2304,
            base_longitude=121.4737,
            anomaly_mode="compressor_fault",
        ),
        DeviceProfile(
            device_id="TRUCK-002",
            route_id="ROUTE-SH-SZ-02",
            secret="cold-chain-beta",
            base_temperature_c=4.1,
            base_humidity_pct=71.0,
            base_latitude=31.1204,
            base_longitude=121.5337,
            anomaly_mode="door_risk",
        ),
        DeviceProfile(
            device_id="TRUCK-003",
            route_id="ROUTE-SH-NJ-03",
            secret="cold-chain-gamma",
            base_temperature_c=3.6,
            base_humidity_pct=66.0,
            base_latitude=31.2604,
            base_longitude=121.3937,
            anomaly_mode="rough_road",
        ),
    ]

