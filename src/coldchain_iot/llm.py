from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from coldchain_iot.models import CloudInsight


class LLMAdvisor:
    """Optional OpenAI-compatible narrator with a local fallback."""

    def __init__(self) -> None:
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    def explain(self, event: dict[str, Any]) -> CloudInsight:
        if self.api_key:
            try:
                return self._remote_explain(event)
            except (urllib.error.URLError, TimeoutError, ValueError):
                pass
        return self._local_explain(event)

    def _remote_explain(self, event: dict[str, Any]) -> CloudInsight:
        prompt = (
            "你是冷链物流运维专家，请根据以下边缘事件给出风险级别、简短原因和建议措施，"
            "结果返回 JSON，字段为 level, summary, recommended_action, tags。\n"
            f"事件：{json.dumps(event, ensure_ascii=False)}"
        )
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是物联网冷链运维分析助手。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        result = json.loads(content)
        return CloudInsight(
            device_id=event["packet"]["device_id"],
            level=result["level"],
            summary=result["summary"],
            recommended_action=result["recommended_action"],
            tags=result.get("tags", []),
        )

    def _local_explain(self, event: dict[str, Any]) -> CloudInsight:
        packet = event["packet"]
        alerts = event["alerts"]
        risk = event["edge_risk_score"]
        level = "low"
        if risk >= 70:
            level = "high"
        elif risk >= 45:
            level = "medium"

        cause = "运行平稳"
        action = "继续按 1 分钟频率采样并上传云端。"
        tags = ["local_llm_fallback"]

        if "冷链温度超阈值" in alerts:
            cause = "制冷机组性能下降或箱门密封不良，导致箱内温度明显高于冷链标准。"
            action = "优先检查制冷机组、电源和门封条，并将采样频率提升至 10 秒。"
            tags.extend(["temperature", "urgent"])
        elif "运输途中箱门异常开启" in alerts:
            cause = "运输过程发生非计划开门，存在人为误操作或货物装卸流程异常。"
            action = "核验司机操作轨迹并复盘装卸计划，同时启用视频联动确认。"
            tags.extend(["access", "traceability"])
        elif "车体震动过大" in alerts:
            cause = "道路颠簸或运输姿态异常，可能影响高价值生鲜或药品质量。"
            action = "建议调整行驶路线并降低车速，必要时对易损货品二次复核。"
            tags.extend(["shock", "route"])

        summary = (
            f"{packet['device_id']} 在 {packet['route_id']} 上报风险分 {risk:.1f}，"
            f"主要原因是{cause}"
        )
        return CloudInsight(
            device_id=packet["device_id"],
            level=level,
            summary=summary,
            recommended_action=action,
            tags=tags,
        )

