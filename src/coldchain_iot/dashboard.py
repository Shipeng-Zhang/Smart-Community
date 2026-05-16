from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_dashboard(summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "dashboard_data.json"
    html_path = output_dir / "dashboard.html"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    device_cards = []
    for item in summary["batch"]["device_metrics"]:
        width = max(5, min(100, int(item["compliance_score"])))
        device_cards.append(
            f"""
            <section class="card">
              <h3>{item['device_id']}</h3>
              <p>线路：{item['route_id']}</p>
              <p>平均温度：{item['avg_temperature_c']} ℃</p>
              <p>平均风险：{item['avg_risk_score']}</p>
              <p>告警数：{item['alert_count']}</p>
              <div class="bar"><span style="width:{width}%"></span></div>
              <p>合规得分：{item['compliance_score']}</p>
            </section>
            """
        )

    alert_cards = []
    for alert in summary["recent_alerts"][:10]:
        alert_cards.append(
            f"""
            <li>
              <strong>{alert['device_id']}</strong> | {alert['level']} | {alert['summary']}<br />
              建议：{alert['recommended_action']}
            </li>
            """
        )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>冷链物流云边端协同系统看板</title>
  <style>
    :root {{
      --bg: #f5f0e8;
      --panel: #fff9f0;
      --ink: #1c2a2a;
      --brand: #0f766e;
      --warn: #b45309;
      --danger: #b91c1c;
      --line: #d8cab7;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
      background:
        radial-gradient(circle at top left, #f7d8a7 0, transparent 24%),
        radial-gradient(circle at bottom right, #b8e1dd 0, transparent 28%),
        var(--bg);
      color: var(--ink);
    }}
    header {{
      padding: 40px 24px 16px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: clamp(28px, 4vw, 44px);
    }}
    .subtitle {{
      max-width: 820px;
      line-height: 1.7;
      color: #334155;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      padding: 0 24px 20px;
    }}
    .stat, .card, .panel {{
      background: rgba(255, 249, 240, 0.92);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 12px 30px rgba(28, 42, 42, 0.08);
    }}
    .stat {{
      padding: 18px;
    }}
    .stat span {{
      display: block;
      color: #64748b;
      margin-bottom: 6px;
    }}
    .stat strong {{
      font-size: 28px;
      color: var(--brand);
    }}
    main {{
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 20px;
      padding: 0 24px 28px;
    }}
    .device-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }}
    .card {{
      padding: 18px;
    }}
    .bar {{
      height: 10px;
      background: #e7dccd;
      border-radius: 999px;
      overflow: hidden;
      margin: 14px 0 10px;
    }}
    .bar span {{
      display: block;
      height: 100%;
      background: linear-gradient(90deg, #0f766e, #f59e0b, #dc2626);
    }}
    .panel {{
      padding: 18px;
    }}
    ul {{
      padding-left: 20px;
      line-height: 1.7;
    }}
    @media (max-width: 900px) {{
      main {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>冷链物流云边端协同监测系统</h1>
    <p class="subtitle">面向生鲜和医药运输场景，系统将温湿度、门磁、定位和震动感知部署在端侧，在边缘网关完成签名校验、流式预警和快速处置，在云端完成批量分析、智能解释和管理可视化。</p>
  </header>
  <section class="stats">
    <article class="stat"><span>仿真设备数</span><strong>{summary['simulation']['device_count']}</strong></article>
    <article class="stat"><span>采样记录数</span><strong>{summary['simulation']['record_count']}</strong></article>
    <article class="stat"><span>实时告警数</span><strong>{summary['realtime']['alert_count']}</strong></article>
    <article class="stat"><span>总体合规分</span><strong>{summary['batch']['overall_compliance_score']}</strong></article>
  </section>
  <main>
    <section>
      <div class="device-grid">
        {''.join(device_cards)}
      </div>
    </section>
    <aside class="panel">
      <h2>最新智能告警</h2>
      <ul>{''.join(alert_cards) or '<li>暂无告警</li>'}</ul>
    </aside>
  </main>
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")

