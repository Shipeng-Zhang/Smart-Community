from __future__ import annotations

import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from smartcity_iot.hub import CommunityHub


class SmartCityServer(ThreadingHTTPServer):
    def __init__(self, addr: tuple[str, int], handler_cls, *, hub: CommunityHub, frontend_dir: Path):
        self.hub = hub
        self.frontend_dir = frontend_dir
        super().__init__(addr, handler_cls)


class SmartCityHandler(SimpleHTTPRequestHandler):
    frontend_dir: Path = Path(".")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.frontend_dir), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._json({"ok": True})
            return
        if parsed.path == "/api/snapshot":
            self._json(self.server.hub.snapshot())
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/work-orders/action":
            payload = self._read_json()
            ok, message, order = self.server.hub.apply_order_action(
                order_id=str(payload.get("order_id", "")),
                action=str(payload.get("action", "")),
                actor=str(payload.get("actor", "调度员")),
                note=str(payload.get("note", "")),
            )
            if not ok:
                self._json({"ok": False, "message": message}, status=HTTPStatus.BAD_REQUEST)
                return
            self._json({"ok": True, "message": "操作成功", "order": order})
            return
        if parsed.path == "/api/sim/control":
            payload = self._read_json()
            action = str(payload.get("action", ""))
            if action == "pause":
                self.server.hub.pause()
                self._json({"ok": True, "paused": True})
                return
            if action == "resume":
                self.server.hub.resume()
                self._json({"ok": True, "paused": False})
                return
            if action == "toggle":
                paused = self.server.hub.toggle()
                self._json({"ok": True, "paused": paused})
                return
            if action == "tick":
                self.server.hub.tick()
                self._json({"ok": True, "message": "manual tick"})
                return
            self._json({"ok": False, "message": "未知控制指令"}, status=HTTPStatus.BAD_REQUEST)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")


def run_server(
    *,
    host: str = "0.0.0.0",
    port: int = 8080,
    household_count: int = 24,
    seed: int | None = None,
    tick_seconds: float = 1.2,
) -> None:
    root = Path(__file__).resolve().parents[2]
    frontend_dir = root / "frontend"
    frontend_dir.mkdir(parents=True, exist_ok=True)
    SmartCityHandler.frontend_dir = frontend_dir

    hub = CommunityHub(household_count=household_count, seed=seed, tick_seconds=tick_seconds)
    hub.start()
    server = SmartCityServer((host, port), SmartCityHandler, hub=hub, frontend_dir=frontend_dir)
    print(f"Smart community IoT server running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        hub.stop()
        server.server_close()

