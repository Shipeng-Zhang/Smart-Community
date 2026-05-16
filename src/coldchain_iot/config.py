from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    device_count: int = 12
    steps_per_device: int = 144
    route_count: int = 6
    seed: int = 42


DEFAULT_CONFIG = SimulationConfig()

