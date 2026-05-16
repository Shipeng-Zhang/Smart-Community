from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from coldchain_iot.analytics import BatchAnalyticsEngine
from coldchain_iot.dashboard import write_dashboard
from coldchain_iot.llm import LLMAdvisor
from coldchain_iot.models import ProcessedEvent


class CloudPlatformV2:
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
        self.state: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=12))
        self.insights: list[dict[str, Any]] = []
        self.batch_engine = BatchAnalyticsEngine()
        self.advisor = LLMAdvisor()

    def ingest(self, event: ProcessedEvent) -> None:
        record = event.to_record()
        self.records.append(record)
        packet = record["packet"]
        self.state[packet["device_id"]].append(record)
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

        should_explain = (
            bool(record["alerts"]) or record["edge_risk_score"] >= 56
        ) and packet["sequence_id"] % 6 == 0
        if should_explain and len(self.insights) < 150:
            insight = self.advisor.explain(record).to_dict()
            insight["edge_risk_score"] = record["edge_risk_score"]
            insight["collected_at"] = packet["collected_at"]
            insight["route_id"] = packet["route_id"]
            self.insights.append(insight)

    def _timeline(self) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for record in self.records:
            timestamp = datetime.fromisoformat(record["packet"]["collected_at"])
            slot = timestamp.strftime("%Y-%m-%d %H:00")
            current = buckets.setdefault(
                slot,
                {
                    "slot": slot,
                    "record_count": 0,
                    "alert_count": 0,
                    "avg_risk_score": 0.0,
                    "avg_temperature_c": 0.0,
                },
            )
            current["record_count"] += 1
            current["alert_count"] += len(record["alerts"])
            current["avg_risk_score"] += record["edge_risk_score"]
            current["avg_temperature_c"] += record["packet"]["temperature_c"]

        timeline = []
        for slot in sorted(buckets):
            data = buckets[slot]
            data["avg_risk_score"] = round(data["avg_risk_score"] / data["record_count"], 2)
            data["avg_temperature_c"] = round(data["avg_temperature_c"] / data["record_count"], 2)
            timeline.append(data)
        return timeline

    def _anomaly_distribution(self) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for record in self.records:
            for alert in record["alerts"]:
                counter[alert] += 1
        return dict(counter.most_common())

    def _top_risk_events(self, limit: int = 20) -> list[dict[str, Any]]:
        top = sorted(
            self.records,
            key=lambda item: (
                item["edge_risk_score"],
                len(item["alerts"]),
                item["packet"]["temperature_c"],
            ),
            reverse=True,
        )[:limit]
        results = []
        for record in top:
            results.append(
                {
                    "device_id": record["packet"]["device_id"],
                    "route_id": record["packet"]["route_id"],
                    "collected_at": record["packet"]["collected_at"],
                    "temperature_c": record["packet"]["temperature_c"],
                    "edge_risk_score": record["edge_risk_score"],
                    "alerts": record["alerts"],
                }
            )
        return results

    def finalize(self, *, simulation_meta: dict[str, Any]) -> dict[str, Any]:
        self.conn.commit()
        batch = self.batch_engine.summarize(self.records)
        timeline = self._timeline()
        anomaly_distribution = self._anomaly_distribution()
        top_events = self._top_risk_events()

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
            "peak_risk_score": round(max(item["edge_risk_score"] for item in self.records), 2),
        }

        fleet_health_index = round(
            max(0.0, min(100.0, batch["overall_compliance_score"] * 0.82 + (100 - realtime["alert_count"] * 0.03) * 0.18)),
            2,
        )

        summary = {
            "project_name": "冷链物流云边端协同监测与智能分析系统",
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "simulation": {
                **simulation_meta,
                "record_count": len(self.records),
                "route_count": len({item["packet"]["route_id"] for item in self.records}),
                "device_count": len({item["packet"]["device_id"] for item in self.records}),
            },
            "realtime": realtime,
            "batch": {
                **batch,
                "fleet_health_index": fleet_health_index,
                "anomaly_distribution": anomaly_distribution,
            },
            "timeline": timeline,
            "top_risk_events": top_events,
            "recent_alerts": self.insights[-30:],
        }

        (self.output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.output_dir / "records.json").write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (self.output_dir / "timeline.json").write_text(
            json.dumps(timeline, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_dashboard(summary, self.output_dir)
        return summary

