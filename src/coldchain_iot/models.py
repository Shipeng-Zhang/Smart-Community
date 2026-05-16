from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TelemetryPacket:
    device_id: str
    route_id: str
    sequence_id: int
    collected_at: str
    temperature_c: float
    humidity_pct: float
    latitude: float
    longitude: float
    speed_kmh: float
    door_open: bool
    shock_g: float
    battery_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProcessedEvent:
    packet: TelemetryPacket
    average_temperature_c: float
    average_humidity_pct: float
    temperature_slope: float
    edge_risk_score: float
    stream_tags: list[str]
    alerts: list[str]
    local_action: str
    processing_latency_ms: int
    signature_valid: bool = True

    def to_record(self) -> dict[str, Any]:
        payload = {
            "packet": self.packet.to_dict(),
            "average_temperature_c": round(self.average_temperature_c, 2),
            "average_humidity_pct": round(self.average_humidity_pct, 2),
            "temperature_slope": round(self.temperature_slope, 3),
            "edge_risk_score": round(self.edge_risk_score, 2),
            "stream_tags": self.stream_tags,
            "alerts": self.alerts,
            "local_action": self.local_action,
            "processing_latency_ms": self.processing_latency_ms,
            "signature_valid": self.signature_valid,
        }
        return payload


@dataclass(slots=True)
class CloudInsight:
    device_id: str
    level: str
    summary: str
    recommended_action: str
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

