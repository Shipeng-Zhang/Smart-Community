from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from statistics import mean
from typing import Any


def _score_device(records: list[dict[str, Any]]) -> dict[str, Any]:
    temperatures = [item["packet"]["temperature_c"] for item in records]
    humidities = [item["packet"]["humidity_pct"] for item in records]
    risks = [item["edge_risk_score"] for item in records]
    latencies = [item["processing_latency_ms"] for item in records]
    out_of_range = [temp for temp in temperatures if temp < 2.0 or temp > 8.0]
    alerts = sum(len(item["alerts"]) for item in records)
    compliance = max(
        0.0,
        100.0
        - len(out_of_range) * 2.2
        - alerts * 0.8
        - max(0.0, mean(risks) - 20.0) * 0.9,
    )
    return {
        "device_id": records[0]["packet"]["device_id"],
        "route_id": records[0]["packet"]["route_id"],
        "record_count": len(records),
        "avg_temperature_c": round(mean(temperatures), 2),
        "avg_humidity_pct": round(mean(humidities), 2),
        "avg_risk_score": round(mean(risks), 2),
        "avg_latency_ms": round(mean(latencies), 2),
        "out_of_range_count": len(out_of_range),
        "alert_count": alerts,
        "compliance_score": round(compliance, 2),
    }


class BatchAnalyticsEngine:
    def summarize(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            grouped[record["packet"]["device_id"]].append(record)

        device_groups = list(grouped.values())
        if not device_groups:
            return {"device_metrics": [], "route_overview": [], "overall_compliance_score": 0.0}

        with ProcessPoolExecutor(max_workers=min(4, len(device_groups))) as executor:
            device_metrics = list(executor.map(_score_device, device_groups))

        route_overview = sorted(
            (
                {
                    "route_id": item["route_id"],
                    "device_id": item["device_id"],
                    "compliance_score": item["compliance_score"],
                    "avg_risk_score": item["avg_risk_score"],
                }
                for item in device_metrics
            ),
            key=lambda item: item["compliance_score"],
        )
        overall_score = round(mean(item["compliance_score"] for item in device_metrics), 2)
        return {
            "device_metrics": sorted(device_metrics, key=lambda item: item["compliance_score"]),
            "route_overview": route_overview,
            "overall_compliance_score": overall_score,
        }

