from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from coldchain_iot.cloud import CloudPlatform
from coldchain_iot.device import ColdChainTruckDevice, default_profiles
from coldchain_iot.edge import EdgeGateway


def run_demo(output_dir: str | Path = "outputs", *, steps: int = 48) -> dict[str, object]:
    base_time = datetime(2026, 5, 16, 8, 0, tzinfo=timezone.utc)
    profiles = default_profiles()
    devices = [ColdChainTruckDevice(profile, seed=index + 7) for index, profile in enumerate(profiles)]
    gateway = EdgeGateway({profile.device_id: profile.secret for profile in profiles})
    cloud = CloudPlatform(Path(output_dir))

    for step in range(steps):
        for device in devices:
            envelope = device.generate_envelope(step, base_time)
            event = gateway.ingest(envelope)
            cloud.ingest(event)

    return cloud.finalize()

