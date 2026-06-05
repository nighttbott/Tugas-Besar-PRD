"""
core/database.py
Storage layers:
  • Redis / In-Memory — active sessions + cooldown (fast, ephemeral)
  • PostgreSQL        — handled via core/database_sql.py and SQLAlchemy models
"""
import json
import time
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from .config import get_settings

# ── E-wallet options ──────────────────────────────────────────────────────────
SUPPORTED_EWALLETS = ["GoPay", "OVO", "ShopeePay", "Dana", "LinkAja"]

# ── Gate ID → Location mapping ────────────────────────────────────────────────
GATE_LOCATIONS: dict[str, str] = {
    "G1":    "Parkir Mahasiswa",
    "G2":    "Parkir Utama",
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def _normalize(plate: str) -> str:
    return plate.upper().replace(" ", "")

def gate_location(gate_id: str) -> str:
    """Return human-readable location for a gate ID."""
    return GATE_LOCATIONS.get(gate_id, f"Gerbang {gate_id}")

# ── Redis ─────────────────────────────────────────────────────────────────────
_redis: Optional[aioredis.Redis] = None
_redis_ok: bool = False

# Fallback in-memory storage kalau Redis mati
_mem_sessions: dict[str, str] = {}
_mem_cooldowns: dict[str, float] = {}

async def get_redis() -> Optional[aioredis.Redis]:
    global _redis, _redis_ok
    if _redis is None:
        settings = get_settings()
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    try:
        await _redis.ping()
        _redis_ok = True
    except Exception:
        _redis_ok = False
    return _redis if _redis_ok else None

async def close_redis():
    global _redis, _redis_ok
    if _redis:
        await _redis.aclose()
        _redis = None
    _redis_ok = False

async def check_cooldown(plate: str) -> bool:
    key = f"cooldown:{_normalize(plate)}"
    redis = await get_redis()
    if redis:
        return await redis.exists(key) == 1
    exp = _mem_cooldowns.get(key, 0)
    return time.time() < exp

async def set_cooldown(plate: str):
    key = f"cooldown:{_normalize(plate)}"
    redis = await get_redis()
    settings = get_settings()
    if redis:
        await redis.set(key, "1", ex=settings.REDIS_COOLDOWN_TTL)
    else:
        _mem_cooldowns[key] = time.time() + settings.REDIS_COOLDOWN_TTL

async def get_active_session(plate: str) -> Optional[dict]:
    key = f"session:{_normalize(plate)}"
    redis = await get_redis()
    if redis:
        raw = await redis.get(key)
    else:
        raw = _mem_sessions.get(key)
    return json.loads(raw) if raw else None

async def approve_guest_exit(plate: str) -> bool:
    key = f"session:{_normalize(plate)}"
    redis = await get_redis()
    if redis:
        raw = await redis.get(key)
    else:
        raw = _mem_sessions.get(key)
    if not raw:
        return False
    session = json.loads(raw)
    session["exit_approved"] = True
    payload = json.dumps(session)
    if redis:
        settings = get_settings()
        ttl = await redis.ttl(key)
        await redis.set(key, payload, ex=ttl if ttl > 0 else settings.REDIS_SESSION_TTL)
    else:
        _mem_sessions[key] = payload
    return True

async def flag_manual_payment(plate: str) -> bool:
    key = f"session:{_normalize(plate)}"
    redis = await get_redis()
    if redis:
        raw = await redis.get(key)
    else:
        raw = _mem_sessions.get(key)
    if not raw:
        return False
    session = json.loads(raw)
    session["needs_manual_payment"] = True
    payload = json.dumps(session)
    if redis:
        settings = get_settings()
        ttl = await redis.ttl(key)
        await redis.set(key, payload, ex=ttl if ttl > 0 else settings.REDIS_SESSION_TTL)
    else:
        _mem_sessions[key] = payload
    return True

async def get_all_active_sessions() -> list[dict]:
    redis = await get_redis()
    sessions = []
    if redis:
        keys = await redis.keys("session:*")
        for k in keys:
            raw = await redis.get(k)
            if raw:
                sessions.append(json.loads(raw))
    else:
        for raw in _mem_sessions.values():
            sessions.append(json.loads(raw))
    return sessions

async def create_session(plate: str, gate_id: str, confidence: float, is_guest: bool = False) -> dict:
    key = f"session:{_normalize(plate)}"
    redis = await get_redis()
    settings = get_settings()
    session = {
        "plate":         _normalize(plate),
        "gate_id":       gate_id,
        "gate_location": gate_location(gate_id),
        "confidence":    confidence,
        "entry_time":    datetime.now(timezone.utc).isoformat(),
        "entry_ts":      time.time(),
        "status":        "active",
        "is_guest":      is_guest,
        "exit_approved": False,
    }
    payload = json.dumps(session)
    if redis:
        await redis.set(key, payload, ex=settings.REDIS_SESSION_TTL)
    else:
        _mem_sessions[key] = payload
    return session

async def delete_active_session(plate: str) -> None:
    key = f"session:{_normalize(plate)}"
    redis = await get_redis()
    if redis:
        await redis.delete(key)
    else:
        _mem_sessions.pop(key, None)
