from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\u4e00-\u9fff]{3,24}$")


@dataclass(slots=True)
class SessionInfo:
    token: str
    username: str
    email: str
    expires_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "username": self.username,
            "email": self.email,
            "expires_at": self.expires_at.isoformat(timespec="seconds"),
        }


class AuthManager:
    def __init__(self, *, storage_path: Path | None = None, session_hours: int = 24) -> None:
        root = Path(__file__).resolve().parents[2]
        self.storage_path = storage_path or (root / "data" / "users.json")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_hours = session_hours
        self._users = self._load_users()
        self._sessions: dict[str, SessionInfo] = {}
        if not self._users:
            self._bootstrap_default_admin()

    def _load_users(self) -> dict[str, dict[str, str]]:
        if not self.storage_path.exists():
            return {}
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _save_users(self) -> None:
        self.storage_path.write_text(
            json.dumps(self._users, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _bootstrap_default_admin(self) -> None:
        # Demo-friendly default account for classroom.
        self.register(
            username="admin",
            email="admin@community.local",
            password="Admin@12345",
        )

    def _hash_password(self, password: str, *, salt: bytes | None = None) -> str:
        salt_bytes = salt or os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 200_000)
        return f"pbkdf2_sha256${base64.b64encode(salt_bytes).decode()}${base64.b64encode(digest).decode()}"

    def _verify_password(self, password: str, stored: str) -> bool:
        try:
            scheme, salt_b64, hash_b64 = stored.split("$")
            if scheme != "pbkdf2_sha256":
                return False
            salt = base64.b64decode(salt_b64.encode())
            candidate = self._hash_password(password, salt=salt)
            return hmac.compare_digest(candidate, stored)
        except Exception:
            return False

    def _sanitize_account(self, account: str) -> str:
        return account.strip()

    def register(self, *, username: str, email: str, password: str) -> tuple[bool, str]:
        username = username.strip()
        email = email.strip().lower()
        password = password.strip()

        if not USERNAME_PATTERN.match(username):
            return False, "用户名需为 3-24 位，可包含中英文、数字、下划线。"
        if not EMAIL_PATTERN.match(email):
            return False, "邮箱格式不正确。"
        if len(password) < 8:
            return False, "密码长度至少 8 位。"
        if username in self._users:
            return False, "用户名已存在。"
        if any(user.get("email") == email for user in self._users.values()):
            return False, "邮箱已注册。"

        self._users[username] = {
            "username": username,
            "email": email,
            "password_hash": self._hash_password(password),
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        self._save_users()
        return True, "注册成功"

    def login(self, *, account: str, password: str) -> tuple[bool, str, dict[str, Any] | None]:
        account = self._sanitize_account(account)
        password = password.strip()
        if not account or not password:
            return False, "账号或密码不能为空。", None

        user = self._users.get(account)
        if not user:
            user = next((item for item in self._users.values() if item.get("email") == account.lower()), None)
        if not user:
            return False, "账号不存在。", None
        if not self._verify_password(password, user["password_hash"]):
            return False, "密码错误。", None

        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=self.session_hours)
        session = SessionInfo(
            token=token,
            username=user["username"],
            email=user["email"],
            expires_at=expires_at,
        )
        self._sessions[token] = session
        return True, "登录成功", {
            "token": token,
            "user": {
                "username": session.username,
                "email": session.email,
                "expires_at": session.expires_at.isoformat(timespec="seconds") + "Z",
            },
        }

    def logout(self, token: str) -> None:
        self._sessions.pop(token, None)

    def resolve_user(self, token: str) -> dict[str, str] | None:
        if not token:
            return None
        session = self._sessions.get(token)
        if not session:
            return None
        if session.expires_at <= datetime.utcnow():
            self._sessions.pop(token, None)
            return None
        return {
            "username": session.username,
            "email": session.email,
            "expires_at": session.expires_at.isoformat(timespec="seconds") + "Z",
        }

