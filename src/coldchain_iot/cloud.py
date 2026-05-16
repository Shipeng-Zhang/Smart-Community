from __future__ import annotations

import json
import sqlite3
from collections import defaultdict, deque
from pathlib import Path
from statistics import mean
from typing import Any

from coldchain_iot.analytics import BatchAnalyticsEngine
from coldchain_iot.dashboard import write_dashboard
from coldchain_iot.llm import LLMAdvisor
from coldchain_iot.models import ProcessedEvent


class CloudPlatform:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.output_dir / "cloud.db"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry_events (
                device_id TEXT,
                route_id TEXT,
                sequence_id INTEGER,
                collected_at TEXT,
                temperature_c REAL,
                humidity_pct REAL,
                speed_kmh REAL,
                door_open INTEGER,
                shock_g REAL,
                battery_pct REAL,
                avg_temperature_c REAL,
                avg_humidity_pct REAL,
                temperature_slope REAL,
                edge_risk_score REAL,
                alerts_json TEXT,
                action TEXT,
                processing_latency_ms INTEGER
            )
            """
        )
        self.conn.commit()
        self.records: list[dict[str, Any]] = []
        self.stream_state: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=8))
        self.insights: list[dict[str, Any]] = []
        self.advisor = LLMAdvisor()
        self.batch_engine = BatchAnalyticsEngine()

    def ingest(self, event: ProcessedEvent) -> None:
        record = event.to_record()
        self.records.append(record)
        packet = record["packet"]
        self.stream_state[packet["device_id"]].append(record)
        self.conn.execute(
            """
            INSERT INTO telemetry_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packet["device_id"],
                packet["route_id"],
                packet["sequence_id"],
                packet["collected_at"],
                packet["temperature_c"],
                packet["humidity_pct"],
                packet["speed_kmh"],
                int(packet["door_open"]),
                packet["shock_g"],
                packet["battery_pct"],
                record["average_temperature_c"],
                record["average_humidity_pct"],
                record["temperature_slope"],
                record["edge_risk_score"],
                json.dumps(record["alerts"], ensure_ascii=False),
                record["local_action"],
                record["processing_latency_ms"],
            ),
        )
        self.conn.commit()

        insight = self._stream_insight(record)
        if insight:
            self.insights.append(insight)

    def _stream_insight(self, record: dict[str, Any]) -> dict[str, Any] | None:
        device_id = record["packet"]["device_id"]
        window = self.stream_state[device_id]
        avg_window_risk = mean(item["edge_risk_score"] for item in window)
        should_explain = bool(record["alerts"]) or avg_window_risk >= 48.0
        if not should_explain:
            return None
        insight = self.advisor.explain(record).to_dict()
        insight["avg_window_risk"] = round(avg_window_risk, 2)
        insight["device_id"] = device_id
        return insight

    def finalize(self) -> dict[str, Any]:
        batch = self.batch_engine.summarize(self.records)
        realtime = {
            "alert_count": sum(len(item["alerts"]) for item in self.records),
            "avg_edge_latency_ms": round(mean(item["processing_latency_ms"] for item in self.records), 2),
            "high_risk_devices": sorted(
                {
                    item["packet"]["device_id"]
                    for item in self.records
                    if item["edge_risk_score"] >= 60
                }
            ),
        }
        summary = {
            "project_name": "冷链物流云边端协同监测与智能分析系统",
            "simulation": {
                "device_count": len({item["packet"]["device_id"] for item in self.records}),
                "record_count": len(self.records),
            },
            "realtime": realtime,
            "batch": batch,
            "recent_alerts": self.insights[-12:],
        }
        (self.output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.output_dir / "records.json").write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_dashboard(summary, self.output_dir)
        return summary
