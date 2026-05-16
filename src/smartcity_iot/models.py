from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class HouseholdProfile:
    unit_id: str
    building_id: str
    floor: int
    household_type: str
    residents: int
    has_elderly: bool
    vulnerability: float
    base_load_w: float
    base_temp_c: float
    base_humidity_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TelemetrySnapshot:
    unit_id: str
    building_id: str
    floor: int
    household_type: str
    timestamp: str
    temperature_c: float
    humidity_pct: float
    gas_ppm: float
    smoke_ppm: float
    pm25: float
    power_w: float
    power_delta_w: float
    energy_today_kwh: float
    water_leak: bool
    door_open: bool
    occupancy: bool
    motion_count: int
    motion_silence_ticks: int
    risk_score: float
    health_score: float
    mode: str
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["risk_score"] = round(self.risk_score, 2)
        payload["health_score"] = round(self.health_score, 2)
        return payload


@dataclass(slots=True)
class AlertRecord:
    alert_id: str
    unit_id: str
    building_id: str
    kind: str
    severity: int
    title: str
    summary: str
    recommendation: str
    created_at: str
    status: str
    order_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WorkOrder:
    order_id: str
    unit_id: str
    building_id: str
    kind: str
    severity: int
    title: str
    description: str
    status: str
    assignee: str
    priority: str
    created_at: str
    updated_at: str
    due_at: str
    progress_pct: int
    occurrences: int = 1
    history: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Notification:
    note_id: str
    level: str
    title: str
    message: str
    created_at: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

