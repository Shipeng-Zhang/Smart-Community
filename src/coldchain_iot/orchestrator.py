from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from coldchain_iot.config import DEFAULT_CONFIG, SimulationConfig
from coldchain_iot.edge import EdgeGateway
from coldchain_iot.fleet import build_fleet
from coldchain_iot.platform import CloudPlatformV2


def run_simulation(
    output_dir: str | Path = "outputs",
    *,
    config: SimulationConfig | None = None,
) -> dict[str, Any]:
    cfg = config or DEFAULT_CONFIG
    base_time = datetime(2026, 5, 16, 0, 0, tzinfo=timezone.utc)
    profiles, devices = build_fleet(
        device_count=cfg.device_count,
        route_count=cfg.route_count,
        seed=cfg.seed,
    )
    gateway = EdgeGateway({profile.device_id: profile.secret for profile in profiles})
    cloud = CloudPlatformV2(Path(output_dir))

    for step in range(cfg.steps_per_device):
        for device in devices:
            envelope = device.generate_envelope(step, base_time)
            event = gateway.ingest(envelope)
            cloud.ingest(event)

    return cloud.finalize(
        simulation_meta={
            "device_count_requested": cfg.device_count,
            "steps_per_device": cfg.steps_per_device,
            "route_count_requested": cfg.route_count,
            "seed": cfg.seed,
        }
    )

