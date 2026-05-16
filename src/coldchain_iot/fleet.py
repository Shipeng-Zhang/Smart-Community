from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from coldchain_iot.models import TelemetryPacket
from coldchain_iot.security import sign_envelope


ANOMALY_MODES = (
    "compressor_fault",
    "door_risk",
    "rough_road",
    "battery_low",
    "sensor_drift",
    "normal",
)


@dataclass(frozen=True, slots=True)
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
        phase = (step / 10) + (hash(self.profile.route_id) % 7)
        lat = self.profile.base_latitude + 0.02 * math.sin(phase)
        lon = self.profile.base_longitude + 0.018 * math.cos(phase / 1.4)
        return round(lat, 6), round(lon, 6)

    def _temperature(self, step: int) -> float:
        temp = self.profile.base_temperature_c + 0.35 * math.sin(step / 6)
        if self.profile.anomaly_mode == "compressor_fault":
            if 30 <= step <= 58 or 120 <= step <= 148:
                temp += 2.8 + 0.08 * (step % 10)
        elif self.profile.anomaly_mode == "sensor_drift":
            temp += 0.02 * step
        elif self.profile.anomaly_mode == "door_risk":
            if step in {44, 45, 46, 92}:
                temp += 2.0
        elif self.profile.anomaly_mode == "normal":
            temp += 0.12 * math.sin(step / 17)
        return round(temp, 2)

    def _humidity(self, step: int) -> float:
        humidity = self.profile.base_humidity_pct + 3.2 * math.cos(step / 8)
        if self.profile.anomaly_mode == "compressor_fault" and 30 <= step <= 58:
            humidity += 5.0
        if self.profile.anomaly_mode == "sensor_drift":
            humidity += 0.05 * step
        return round(max(35.0, min(98.0, humidity)), 2)

    def _door_open(self, step: int) -> bool:
        if self.profile.anomaly_mode != "door_risk":
            return False
        return step in {44, 45, 92}

    def _shock_g(self, step: int) -> float:
        base = 0.15 + abs(math.sin(step / 5)) * 0.13
        if self.profile.anomaly_mode == "rough_road" and step in {24, 25, 26, 72, 73, 74}:
            base += 1.15
        if self.profile.anomaly_mode == "door_risk" and step in {44, 92}:
            base += 0.8
        return round(base, 2)

    def _speed_kmh(self, step: int) -> float:
        speed = 48.0 + 7.0 * math.sin(step / 11)
        if self.profile.anomaly_mode == "door_risk" and self._door_open(step):
            speed -= 12.0
        if self.profile.anomaly_mode == "rough_road" and step in {24, 25, 26, 72, 73, 74}:
            speed -= 8.0
        return round(max(8.0, speed), 2)

    def _battery_pct(self, step: int) -> float:
        drain = 0.18 + (0.08 if self.profile.anomaly_mode == "battery_low" else 0.0)
        return round(max(18.0, 99.0 - step * drain + self.random.uniform(-0.25, 0.25)), 2)

    def generate_envelope(self, step: int, base_time: datetime) -> dict[str, object]:
        lat, lon = self._route_position(step)
        packet = TelemetryPacket(
            device_id=self.profile.device_id,
            route_id=self.profile.route_id,
            sequence_id=step,
            collected_at=(base_time + timedelta(minutes=step)).astimezone(timezone.utc).isoformat(),
            temperature_c=self._temperature(step),
            humidity_pct=self._humidity(step),
            latitude=lat,
            longitude=lon,
            speed_kmh=self._speed_kmh(step),
            door_open=self._door_open(step),
            shock_g=self._shock_g(step),
            battery_pct=self._battery_pct(step),
        )
        return sign_envelope(
            packet.to_dict(),
            self.profile.secret,
            timestamp=int((base_time + timedelta(minutes=step)).timestamp()),
            nonce=f"{self.profile.device_id}-{step:04d}",
        )


def build_fleet(
    *,
    device_count: int = 16,
    route_count: int = 8,
    seed: int = 42,
) -> tuple[list[DeviceProfile], list[ColdChainTruckDevice]]:
    rng = random.Random(seed)
    route_count = max(1, route_count)
    device_count = max(1, device_count)
    profiles: list[DeviceProfile] = []
    devices: list[ColdChainTruckDevice] = []
    route_centers = [
        (31.2304 + 0.03 * (idx % 4), 121.4737 + 0.03 * (idx // 4))
        for idx in range(route_count)
    ]

    for idx in range(device_count):
        route_index = idx % route_count
        lat, lon = route_centers[route_index]
        anomaly_mode = ANOMALY_MODES[idx % len(ANOMALY_MODES)]
        profile = DeviceProfile(
            device_id=f"TRUCK-{idx + 1:03d}",
            route_id=f"ROUTE-{route_index + 1:02d}",
            secret=f"cold-chain-{idx + 1:03d}",
            base_temperature_c=2.8 + 0.25 * (route_index % 5) + rng.uniform(-0.15, 0.15),
            base_humidity_pct=63.0 + 2.0 * (route_index % 4) + rng.uniform(-1.2, 1.2),
            base_latitude=lat,
            base_longitude=lon,
            anomaly_mode=anomaly_mode,
        )
        profiles.append(profile)
        devices.append(ColdChainTruckDevice(profile, seed=seed + idx * 17))

    return profiles, devices


def default_fleet() -> tuple[list[DeviceProfile], list[ColdChainTruckDevice]]:
    return build_fleet()

