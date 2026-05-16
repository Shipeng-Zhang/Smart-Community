from __future__ import annotations

from collections import defaultdict, deque
from statistics import mean
from typing import Any

from coldchain_iot.models import ProcessedEvent, TelemetryPacket
from coldchain_iot.security import verify_envelope


class EdgeGateway:
    def __init__(self, device_secrets: dict[str, str]) -> None:
        self.device_secrets = device_secrets
        self.temperature_windows: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=5))
        self.humidity_windows: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=5))
        self.recent_sequences: dict[str, deque[int]] = defaultdict(lambda: deque(maxlen=16))

    def ingest(self, envelope: dict[str, Any]) -> ProcessedEvent:
        payload = envelope["payload"]
        device_id = payload["device_id"]
        secret = self.device_secrets[device_id]
        valid, _ = verify_envelope(envelope, secret, now=int(envelope["timestamp"]))
        packet = TelemetryPacket(**payload)

        if packet.sequence_id in self.recent_sequences[device_id]:
            raise ValueError(f"duplicate sequence detected for {device_id}")
        self.recent_sequences[device_id].append(packet.sequence_id)

        temp_window = self.temperature_windows[device_id]
        humidity_window = self.humidity_windows[device_id]
        temp_window.append(packet.temperature_c)
        humidity_window.append(packet.humidity_pct)

        avg_temp = mean(temp_window)
        avg_humidity = mean(humidity_window)
        slope = 0.0
        if len(temp_window) >= 2:
            slope = (temp_window[-1] - temp_window[0]) / (len(temp_window) - 1)

        alerts: list[str] = []
        tags: list[str] = ["streaming", "edge_preprocessed"]
        risk = 8.0

        if not valid:
            alerts.append("设备签名校验失败")
            tags.append("security")
            risk += 45.0
        if packet.temperature_c < 2.0 or packet.temperature_c > 8.0:
            alerts.append("冷链温度超阈值")
            tags.append("temperature")
            risk += 35.0
        if avg_temp > 6.0:
            alerts.append("温度均值持续偏高")
            tags.append("thermal_drift")
            risk += 18.0
        if slope > 0.6:
            alerts.append("短时温升过快")
            tags.append("trend")
            risk += 16.0
        if packet.door_open:
            alerts.append("运输途中箱门异常开启")
            tags.append("access")
            risk += 18.0
        if packet.shock_g >= 1.0:
            alerts.append("车体震动过大")
            tags.append("shock")
            risk += 14.0
        if packet.battery_pct < 84.0:
            alerts.append("设备电量偏低")
            tags.append("maintenance")
            risk += 8.0

        if not alerts:
            tags.append("healthy")

        if risk >= 72:
            action = "边缘侧立即触发声光告警，并要求司机检查制冷机组。"
        elif risk >= 45:
            action = "边缘侧下发复检指令，提升上报频率并通知值班人员。"
        else:
            action = "边缘侧保持常规采样，按计划同步至云端。"

        latency_ms = int(12 + len(temp_window) * 4 + max(0, packet.temperature_c - 5.0) * 5 + packet.shock_g * 6)

        return ProcessedEvent(
            packet=packet,
            average_temperature_c=avg_temp,
            average_humidity_pct=avg_humidity,
            temperature_slope=slope,
            edge_risk_score=min(100.0, risk),
            stream_tags=sorted(set(tags)),
            alerts=alerts,
            local_action=action,
            processing_latency_ms=latency_ms,
            signature_valid=valid,
        )

