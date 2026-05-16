from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sign_envelope(
    payload: dict[str, Any],
    secret: str,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    ts = int(time.time()) if timestamp is None else int(timestamp)
    envelope_nonce = nonce or hashlib.sha1(f"{payload.get('device_id')}:{payload.get('sequence_id')}:{ts}".encode()).hexdigest()[:16]
    message = f"{ts}.{envelope_nonce}.{canonical_json(payload)}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return {
        "timestamp": ts,
        "nonce": envelope_nonce,
        "signature": signature,
        "payload": payload,
    }


def verify_envelope(
    envelope: dict[str, Any],
    secret: str,
    *,
    now: int | None = None,
    max_age_seconds: int = 600,
) -> tuple[bool, str]:
    required_keys = {"timestamp", "nonce", "signature", "payload"}
    if not required_keys.issubset(envelope):
        return False, "missing_fields"
    ts = int(envelope["timestamp"])
    current = int(time.time()) if now is None else int(now)
    if abs(current - ts) > max_age_seconds:
        return False, "expired"
    message = f"{ts}.{envelope['nonce']}.{canonical_json(envelope['payload'])}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(envelope["signature"])):
        return False, "bad_signature"
    return True, "ok"

