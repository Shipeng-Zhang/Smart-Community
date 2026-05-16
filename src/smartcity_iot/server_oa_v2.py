from __future__ import annotations

import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from smartcity_iot.auth import AuthManager
from smartcity_iot.hub import CommunityHub


class SmartCityOAV2HTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        addr: tuple[str, int],
        handler_cls,
        *,
        hub: CommunityHub,
        auth_manager: AuthManager,
        frontend_dir: Path,
    ):
        self.hub = hub
        self.auth_manager = auth_manager
        self.frontend_dir = frontend_dir
        super().__init__(addr, handler_cls)


class SmartCityOAV2Handler(SimpleHTTPRequestHandler):
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

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _auth_token(self) -> str:
        auth_header = self.headers.get("Authorization", "").strip()
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()
        return self.headers.get("X-Auth-Token", "").strip()

    def _current_user(self) -> dict[str, str] | None:
        return self.server.auth_manager.resolve_user(self._auth_token())

    def _require_auth(self) -> dict[str, str] | None:
        user = self._current_user()
        if not user:
            self._json({"ok": False, "message": "未登录或登录已过期"}, status=HTTPStatus.UNAUTHORIZED)
            return None
        return user

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"", "/"}:
            self._redirect("/login.html")
            return
        if parsed.path == "/login":
            self._redirect("/login.html")
            return
        if parsed.path == "/register":
            self._redirect("/register.html")
            return

        if parsed.path == "/api/health":
            self._json({"ok": True})
            return

        if parsed.path == "/api/auth/me":
            user = self._require_auth()
            if not user:
                return
            self._json({"ok": True, "user": user})
            return

        if parsed.path == "/api/snapshot":
            if not self._require_auth():
                return
            self._json(self.server.hub.snapshot())
            return

        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/auth/login":
            payload = self._read_json()
            ok, message, result = self.server.auth_manager.login(
                account=str(payload.get("account", "")),
                password=str(payload.get("password", "")),
            )
            if not ok or not result:
                self._json({"ok": False, "message": message}, status=HTTPStatus.BAD_REQUEST)
                return
            self._json({"ok": True, "message": message, **result})
            return

        if parsed.path == "/api/auth/register":
            payload = self._read_json()
            ok, message = self.server.auth_manager.register(
                username=str(payload.get("username", "")),
                email=str(payload.get("email", "")),
                password=str(payload.get("password", "")),
            )
            if not ok:
                self._json({"ok": False, "message": message}, status=HTTPStatus.BAD_REQUEST)
                return
            self._json({"ok": True, "message": message})
            return

        if parsed.path == "/api/auth/logout":
            token = self._auth_token()
            if token:
                self.server.auth_manager.logout(token)
            self._json({"ok": True, "message": "已退出登录"})
            return

        if parsed.path == "/api/work-orders/action":
            user = self._require_auth()
            if not user:
                return
            payload = self._read_json()
            ok, message, order = self.server.hub.apply_order_action(
                order_id=str(payload.get("order_id", "")),
                action=str(payload.get("action", "")),
                actor=str(payload.get("actor") or user["username"]),
                note=str(payload.get("note", "")),
            )
            if not ok:
                self._json({"ok": False, "message": message}, status=HTTPStatus.BAD_REQUEST)
                return
            self._json({"ok": True, "message": "操作成功", "order": order})
            return

        if parsed.path == "/api/sim/control":
            if not self._require_auth():
                return
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
    frontend_dir = root / "frontend_oa_v2"
    frontend_dir.mkdir(parents=True, exist_ok=True)
    SmartCityOAV2Handler.frontend_dir = frontend_dir

    hub = CommunityHub(household_count=household_count, seed=seed, tick_seconds=tick_seconds)
    auth_manager = AuthManager()
    hub.start()
    server = SmartCityOAV2HTTPServer(
        (host, port),
        SmartCityOAV2Handler,
        hub=hub,
        auth_manager=auth_manager,
        frontend_dir=frontend_dir,
    )
    print(f"Smart community OA v2 dashboard running at http://127.0.0.1:{port}")
    print(f"Login page: http://127.0.0.1:{port}/login.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        hub.stop()
        server.server_close()
