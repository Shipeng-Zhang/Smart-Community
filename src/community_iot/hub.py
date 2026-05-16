from __future__ import annotations

import threading
import time
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from community_iot.models import AlertRecord, Notification, TelemetrySnapshot, WorkOrder
from community_iot.simulator import CommunitySimulator, build_profiles


OPEN_STATUSES = {"new", "assigned", "processing", "resolved"}
SEVERITY_LABEL = {1: "低", 2: "较低", 3: "中", 4: "高", 5: "紧急"}
PRIORITY_MAP = {1: "P4", 2: "P3", 3: "P2", 4: "P1", 5: "P0"}
ASSIGNEE_MAP = {
    "gas_leak": "安全巡检组",
    "smoke_high": "消防联动组",
    "power_overload": "电力维护组",
    "water_leak": "管网维护组",
    "elderly_care": "网格服务组",
    "night_security": "安保值班组",
    "air_quality": "环境治理组",
}


class CommunityOpsHub:
    def __init__(
        self,
        *,
        household_count: int = 24,
        seed: int | None = None,
        tick_seconds: float = 1.2,
    ) -> None:
        self.tick_seconds = tick_seconds
        self.seed = seed
        self._lock = threading.RLock()
        self._paused = False
        self._running = False
        self._worker: threading.Thread | None = None

        profiles = build_profiles(household_count=household_count, seed=seed)
        self._profiles = {item.unit_id: item for item in profiles}
        self._simulator = CommunitySimulator(profiles, seed=seed)
        self._tick_index = 0
        self._sim_time = self._simulator.sim_time

        self._latest: dict[str, TelemetrySnapshot] = {}
        self._alerts: deque[AlertRecord] = deque(maxlen=900)
        self._orders: dict[str, WorkOrder] = {}
        self._notifications: deque[Notification] = deque(maxlen=400)
        self._trend: deque[dict[str, Any]] = deque(maxlen=220)
        self._cooldowns: dict[tuple[str, str], int] = {}
        self._open_order_by_key: dict[tuple[str, str], str] = {}

        self._alert_seq = 0
        self._order_seq = 0
        self._note_seq = 0

    @property
    def paused(self) -> bool:
        return self._paused

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._run_loop, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._running = False
        worker = self._worker
        if worker and worker.is_alive():
            worker.join(timeout=2)
        self._worker = None

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def toggle(self) -> bool:
        self._paused = not self._paused
        return self._paused

    def _run_loop(self) -> None:
        while self._running:
            if not self._paused:
                self.tick()
            time.sleep(self.tick_seconds)

    def tick(self) -> None:
        with self._lock:
            snapshots, sim_time = self._simulator.step()
            self._tick_index += 1
            self._sim_time = sim_time
            new_alerts_this_tick = 0

            for snapshot in snapshots:
                previous = self._latest.get(snapshot.unit_id)
                self._latest[snapshot.unit_id] = snapshot
                alert_specs = self._detect_alerts(snapshot, previous)
                if not alert_specs:
                    continue
                for spec in alert_specs:
                    self._ingest_alert(snapshot, *spec)
                    new_alerts_this_tick += 1

            self._auto_escalate_orders()
            self._auto_close_resolved_orders()
            self._append_trend(new_alerts_this_tick)

    def _next_alert_id(self) -> str:
        self._alert_seq += 1
        return f"ALT-{self._alert_seq:06d}"

    def _next_order_id(self) -> str:
        self._order_seq += 1
        return f"WO-{self._order_seq:06d}"

    def _next_note_id(self) -> str:
        self._note_seq += 1
        return f"N-{self._note_seq:06d}"

    def _detect_alerts(
        self, current: TelemetrySnapshot, previous: TelemetrySnapshot | None
    ) -> list[tuple[str, int, str, str, str]]:
        hour = datetime.fromisoformat(current.timestamp).hour
        specs: list[tuple[str, int, str, str, str]] = []
        delta_gas = current.gas_ppm - (previous.gas_ppm if previous else current.gas_ppm)
        delta_smoke = current.smoke_ppm - (previous.smoke_ppm if previous else current.smoke_ppm)

        if current.gas_ppm >= 24 or (current.gas_ppm >= 18 and delta_gas >= 8):
            severity = min(5, 3 + int((current.gas_ppm - 20) / 8))
            specs.append(
                (
                    "gas_leak",
                    severity,
                    "疑似燃气泄漏",
                    f"{current.unit_id} 燃气浓度达到 {current.gas_ppm} ppm，存在明火或管道泄漏风险。",
                    "建议立即开启通风、关闭阀门，并派安全巡检组入户复核。",
                )
            )

        if current.smoke_ppm >= 55 or current.pm25 >= 140 or delta_smoke >= 18:
            severity = min(5, 2 + int(max(current.smoke_ppm - 45, current.pm25 - 130) / 25))
            specs.append(
                (
                    "smoke_high",
                    severity,
                    "烟雾/颗粒物超标",
                    f"{current.unit_id} 烟雾值 {current.smoke_ppm} ppm，PM2.5 {current.pm25}，可能由油烟滞留或电器冒烟引起。",
                    "建议联系住户检查厨房排风设备，必要时触发消防联动预警。",
                )
            )

        if current.power_w >= 4200 or current.power_delta_w >= 1500:
            severity = min(5, 2 + int((max(current.power_w - 3800, current.power_delta_w - 1200)) / 700))
            specs.append(
                (
                    "power_overload",
                    severity,
                    "疑似用电过载",
                    f"{current.unit_id} 实时功率 {current.power_w} W，突增 {current.power_delta_w} W，存在线路过载风险。",
                    "建议远程降载并安排电工检查配电箱及大功率电器。",
                )
            )

        if current.water_leak:
            specs.append(
                (
                    "water_leak",
                    4,
                    "管网渗漏告警",
                    f"{current.unit_id} 检测到持续漏水信号，可能导致楼层渗漏和财产损失。",
                    "建议立即派管网维护组上门排查，必要时先关闭入户阀门。",
                )
            )

        if (
            self._profiles[current.unit_id].has_elderly
            and current.occupancy
            and current.motion_silence_ticks >= 6
        ):
            specs.append(
                (
                    "elderly_care",
                    3,
                    "老人户低活动异常",
                    f"{current.unit_id} 连续 {current.motion_silence_ticks} 个采样周期几乎无活动。",
                    "建议由网格服务组电话回访或上门确认老人状态。",
                )
            )

        if current.pm25 >= 160 and not current.door_open:
            specs.append(
                (
                    "air_quality",
                    3,
                    "室内空气质量偏差",
                    f"{current.unit_id} PM2.5 达到 {current.pm25}，长时间暴露可能影响健康。",
                    "建议提醒住户开启新风或开窗通风，并复检厨房排烟系统。",
                )
            )

        if current.door_open and not current.occupancy and (hour >= 23 or hour <= 5):
            specs.append(
                (
                    "night_security",
                    3,
                    "夜间门磁异常",
                    f"{current.unit_id} 夜间无人状态下门磁被触发，可能存在入侵风险。",
                    "建议安保值班组结合门禁和视频进行联动核验。",
                )
            )

        filtered: list[tuple[str, int, str, str, str]] = []
        for spec in specs:
            key = (current.unit_id, spec[0])
            last_tick = self._cooldowns.get(key, -99)
            if self._tick_index - last_tick >= 3:
                self._cooldowns[key] = self._tick_index
                filtered.append(spec)
        return filtered

    def _ingest_alert(
        self,
        snapshot: TelemetrySnapshot,
        kind: str,
        severity: int,
        title: str,
        summary: str,
        recommendation: str,
    ) -> None:
        alert_id = self._next_alert_id()
        order_id = self._upsert_order(snapshot, kind, severity, title, recommendation)
        alert = AlertRecord(
            alert_id=alert_id,
            unit_id=snapshot.unit_id,
            building_id=snapshot.building_id,
            kind=kind,
            severity=severity,
            title=title,
            summary=summary,
            recommendation=recommendation,
            created_at=snapshot.timestamp,
            status="open",
            order_id=order_id,
        )
        self._alerts.appendleft(alert)
        self._push_notification(
            level="warning" if severity <= 3 else "critical",
            title=f"{title}（{SEVERITY_LABEL.get(severity, '中')}）",
            message=f"{summary} 已自动生成工单 {order_id}。",
            source=snapshot.unit_id,
        )

    def _upsert_order(
        self,
        snapshot: TelemetrySnapshot,
        kind: str,
        severity: int,
        title: str,
        recommendation: str,
    ) -> str:
        key = (snapshot.unit_id, kind)
        existing_id = self._open_order_by_key.get(key)
        if existing_id and existing_id in self._orders:
            order = self._orders[existing_id]
            if order.status in OPEN_STATUSES:
                order.occurrences += 1
                order.severity = max(order.severity, severity)
                order.priority = PRIORITY_MAP.get(order.severity, "P2")
                order.updated_at = snapshot.timestamp
                order.progress_pct = min(95, max(order.progress_pct, 30))
                order.description = recommendation
                order.history.append(
                    {
                        "time": snapshot.timestamp,
                        "actor": "EdgeEngine",
                        "action": "repeat_alert",
                        "note": f"重复告警累计 {order.occurrences} 次。",
                    }
                )
                return order.order_id

        order_id = self._next_order_id()
        due_at = datetime.fromisoformat(snapshot.timestamp) + timedelta(minutes=20 + (5 - severity) * 8)
        order = WorkOrder(
            order_id=order_id,
            unit_id=snapshot.unit_id,
            building_id=snapshot.building_id,
            kind=kind,
            severity=severity,
            title=title,
            description=recommendation,
            status="new",
            assignee=ASSIGNEE_MAP.get(kind, "综合运维组"),
            priority=PRIORITY_MAP.get(severity, "P2"),
            created_at=snapshot.timestamp,
            updated_at=snapshot.timestamp,
            due_at=due_at.isoformat(timespec="seconds"),
            progress_pct=8,
            history=[
                {
                    "time": snapshot.timestamp,
                    "actor": "EdgeEngine",
                    "action": "create",
                    "note": "边缘规则引擎自动建单。",
                }
            ],
        )
        self._orders[order_id] = order
        self._open_order_by_key[key] = order_id
        return order_id

    def _push_notification(self, *, level: str, title: str, message: str, source: str) -> None:
        note = Notification(
            note_id=self._next_note_id(),
            level=level,
            title=title,
            message=message,
            created_at=self._sim_time.isoformat(timespec="seconds"),
            source=source,
        )
        self._notifications.appendleft(note)

    def _auto_escalate_orders(self) -> None:
        now = self._sim_time
        for order in self._orders.values():
            if order.status not in {"new", "assigned", "processing"}:
                continue
            if datetime.fromisoformat(order.due_at) <= now:
                previous = order.status
                if previous == "new":
                    order.status = "assigned"
                    order.progress_pct = max(order.progress_pct, 25)
                elif previous == "assigned":
                    order.status = "processing"
                    order.progress_pct = max(order.progress_pct, 55)
                else:
                    order.severity = min(5, order.severity + 1)
                    order.priority = PRIORITY_MAP.get(order.severity, order.priority)
                order.updated_at = now.isoformat(timespec="seconds")
                order.history.append(
                    {
                        "time": order.updated_at,
                        "actor": "DispatchBot",
                        "action": "escalate",
                        "note": "工单接近/超过 SLA，系统自动升级处理。",
                    }
                )
                self._push_notification(
                    level="critical" if order.severity >= 4 else "warning",
                    title=f"工单 {order.order_id} 自动升级",
                    message=f"{order.unit_id} 的 {order.title} 处理超时，状态已从 {previous} 调整为 {order.status}。",
                    source=order.unit_id,
                )
                due_next = now + timedelta(minutes=max(10, 35 - order.severity * 5))
                order.due_at = due_next.isoformat(timespec="seconds")

    def _auto_close_resolved_orders(self) -> None:
        now = self._sim_time
        for order in self._orders.values():
            if order.status != "resolved":
                continue
            updated = datetime.fromisoformat(order.updated_at)
            if now - updated >= timedelta(minutes=15):
                order.status = "closed"
                order.progress_pct = 100
                order.updated_at = now.isoformat(timespec="seconds")
                order.history.append(
                    {
                        "time": order.updated_at,
                        "actor": "CloseBot",
                        "action": "auto_close",
                        "note": "持续稳定 15 分钟，系统自动闭环。",
                    }
                )
                self._push_notification(
                    level="info",
                    title=f"工单 {order.order_id} 自动闭环",
                    message=f"{order.unit_id} 当前指标恢复稳定，工单已自动闭环。",
                    source=order.unit_id,
                )

    def _append_trend(self, new_alerts: int) -> None:
        if not self._latest:
            return
        avg_risk = mean(item.risk_score for item in self._latest.values())
        total_power_kw = sum(item.power_w for item in self._latest.values()) / 1000
        open_orders = sum(1 for item in self._orders.values() if item.status in OPEN_STATUSES)
        self._trend.append(
            {
                "tick": self._tick_index,
                "time": self._sim_time.strftime("%H:%M"),
                "avg_risk_score": round(avg_risk, 2),
                "total_power_kw": round(total_power_kw, 2),
                "open_orders": open_orders,
                "new_alerts": new_alerts,
            }
        )

    def _workflow_counts(self) -> dict[str, int]:
        counts = Counter(item.status for item in self._orders.values())
        return {
            "new": counts.get("new", 0),
            "assigned": counts.get("assigned", 0),
            "processing": counts.get("processing", 0),
            "resolved": counts.get("resolved", 0),
            "closed": counts.get("closed", 0),
        }

    def _building_cards(self) -> list[dict[str, Any]]:
        by_building: dict[str, list[TelemetrySnapshot]] = defaultdict(list)
        for reading in self._latest.values():
            by_building[reading.building_id].append(reading)

        cards: list[dict[str, Any]] = []
        for building, readings in sorted(by_building.items()):
            avg_risk = mean(item.risk_score for item in readings)
            energy = sum(item.energy_today_kwh for item in readings)
            unit_ids = {item.unit_id for item in readings}
            building_orders = [
                order
                for order in self._orders.values()
                if order.building_id == building and order.status in OPEN_STATUSES
            ]
            cards.append(
                {
                    "building_id": building,
                    "household_count": len(unit_ids),
                    "avg_risk_score": round(avg_risk, 2),
                    "energy_today_kwh": round(energy, 2),
                    "open_orders": len(building_orders),
                    "critical_orders": sum(1 for item in building_orders if item.severity >= 4),
                }
            )
        return cards

    def _kpis(self) -> dict[str, Any]:
        latest = list(self._latest.values())
        household_count = len(self._profiles)
        open_orders = [item for item in self._orders.values() if item.status in OPEN_STATUSES]
        overdue_count = sum(1 for item in open_orders if datetime.fromisoformat(item.due_at) <= self._sim_time)
        alerts_recent = [
            item
            for item in self._alerts
            if datetime.fromisoformat(item.created_at) >= self._sim_time - timedelta(minutes=60)
        ]
        avg_risk = mean(item.risk_score for item in latest) if latest else 0
        total_energy = sum(item.energy_today_kwh for item in latest)
        avg_temp = mean(item.temperature_c for item in latest) if latest else 0
        avg_humidity = mean(item.humidity_pct for item in latest) if latest else 0
        safety_score = max(0.0, 100 - avg_risk * 0.78 - len(open_orders) * 1.2 - overdue_count * 2.4)

        return {
            "household_count": household_count,
            "active_device_count": household_count * 7,
            "open_order_count": len(open_orders),
            "overdue_order_count": overdue_count,
            "alerts_last_hour": len(alerts_recent),
            "avg_risk_score": round(avg_risk, 2),
            "safety_score": round(safety_score, 2),
            "total_energy_today_kwh": round(total_energy, 2),
            "avg_temperature_c": round(avg_temp, 2),
            "avg_humidity_pct": round(avg_humidity, 2),
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latest_units = sorted(self._latest.values(), key=lambda item: item.risk_score, reverse=True)
            orders = sorted(
                self._orders.values(),
                key=lambda item: (
                    {"new": 0, "assigned": 1, "processing": 2, "resolved": 3, "closed": 4}.get(item.status, 9),
                    -item.severity,
                    item.updated_at,
                ),
            )
            alerts = list(self._alerts)[:40]
            notes = list(self._notifications)[:40]
            return {
                "system_name": "智慧社区居家安全与能耗协同管理系统",
                "challenge_point": "老旧社区厨房用气用电安全与物业工单闭环效率",
                "simulation": {
                    "tick_index": self._tick_index,
                    "sim_time": self._sim_time.isoformat(timespec="seconds"),
                    "tick_seconds": self.tick_seconds,
                    "paused": self._paused,
                },
                "kpis": self._kpis(),
                "workflow_counts": self._workflow_counts(),
                "trend": list(self._trend)[-80:],
                "building_cards": self._building_cards(),
                "work_orders": [item.to_dict() for item in orders[:80]],
                "alerts": [item.to_dict() for item in alerts],
                "notifications": [item.to_dict() for item in notes],
                "units": [item.to_dict() for item in latest_units],
            }

    def apply_order_action(
        self,
        *,
        order_id: str,
        action: str,
        actor: str = "调度员",
        note: str = "",
    ) -> tuple[bool, str, dict[str, Any] | None]:
        with self._lock:
            order = self._orders.get(order_id)
            if not order:
                return False, f"工单 {order_id} 不存在", None

            transition = {
                "assign": {"new", "assigned"},
                "start": {"assigned", "new"},
                "resolve": {"processing", "assigned"},
                "close": {"resolved", "processing"},
                "reopen": {"closed", "resolved"},
                "escalate": {"new", "assigned", "processing"},
            }
            if action not in transition:
                return False, f"不支持动作 {action}", None
            if order.status not in transition[action]:
                return False, f"状态 {order.status} 不支持动作 {action}", None

            now = self._sim_time.isoformat(timespec="seconds")
            prev_status = order.status
            if action == "assign":
                order.status = "assigned"
                order.progress_pct = max(order.progress_pct, 25)
            elif action == "start":
                order.status = "processing"
                order.progress_pct = max(order.progress_pct, 55)
            elif action == "resolve":
                order.status = "resolved"
                order.progress_pct = max(order.progress_pct, 88)
            elif action == "close":
                order.status = "closed"
                order.progress_pct = 100
            elif action == "reopen":
                order.status = "processing"
                order.progress_pct = 52
                order.due_at = (self._sim_time + timedelta(minutes=20)).isoformat(timespec="seconds")
            elif action == "escalate":
                order.severity = min(5, order.severity + 1)
                order.priority = PRIORITY_MAP.get(order.severity, order.priority)
                order.progress_pct = max(order.progress_pct, 40)

            order.updated_at = now
            order.history.append(
                {
                    "time": now,
                    "actor": actor,
                    "action": action,
                    "note": note or f"{actor} 执行了 {action}。",
                }
            )

            if action == "reopen":
                self._push_notification(
                    level="warning",
                    title=f"工单 {order.order_id} 重新打开",
                    message=f"{order.unit_id} 的 {order.title} 重新进入处理流程。",
                    source=order.unit_id,
                )
            else:
                self._push_notification(
                    level="info" if action in {"assign", "start"} else "warning",
                    title=f"工单 {order.order_id} 状态更新",
                    message=f"{order.unit_id}：{prev_status} -> {order.status}",
                    source=order.unit_id,
                )
            return True, "ok", order.to_dict()

