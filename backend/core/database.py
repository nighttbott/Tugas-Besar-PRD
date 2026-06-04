"""
core/database.py
Storage layers:
  • Redis        — active sessions + cooldown (fast, ephemeral)
  • db.json      — vehicle registry (persists across restarts)
  • history.json — completed parking sessions (persists across restarts)
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import redis.asyncio as aioredis

from .config import get_settings

# ── Persistence paths ─────────────────────────────────────────────────────────
_DB_FILE      = Path(__file__).parent / "db.json"
_HISTORY_FILE = Path(__file__).parent / "history.json"

# ── E-wallet options ──────────────────────────────────────────────────────────
SUPPORTED_EWALLETS = ["GoPay", "OVO", "ShopeePay", "Dana", "LinkAja"]

# ── Gate ID → Location mapping ────────────────────────────────────────────────
GATE_LOCATIONS: dict[str, str] = {
    "G1":    "Parkir Mahasiswa",
    "G2":    "Parkir Utama",
}

# ── Default seed data ─────────────────────────────────────────────────────────
_DEFAULT_VEHICLES: dict[str, dict] = {
    "D4321ITB": {
        "plate_raw":            "D 4321 ITB",
        "nim":                  "13525001",
        "owner":                "Michael Abduh",
        "vehicle_type":         "motor",
        "model":                "Honda Beat",
        "status":               "active",
        "verification_status":  "verified",
        "verified_at":          "2025-01-01T00:00:00+00:00",
        "verified_gate":        "G1",
        "verification_confidence": 0.95,
        "flag_reason":          None,
        "ewallets": [
            {"provider": "GoPay", "balance": 85000,  "masked_account": "0812****7890", "is_primary": True},
            {"provider": "OVO",   "balance": 120000, "masked_account": "0856****1234", "is_primary": False},
        ],
    },
    "D9876KW": {
        "plate_raw":            "D 9876 KW",
        "nim":                  "13525001",
        "owner":                "Michael Abduh",
        "vehicle_type":         "motor",
        "model":                "Yamaha NMAX",
        "status":               "active",
        "verification_status":  "pending",
        "verified_at":          None,
        "verified_gate":        None,
        "verification_confidence": None,
        "flag_reason":          None,
        "ewallets":             [],
    },
}


# ── Vehicle DB ────────────────────────────────────────────────────────────────
def _load_db() -> dict:
    if _DB_FILE.exists():
        try:
            with open(_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[DB] Warning: db.json corrupted ({e}), resetting to defaults.")
    _write_json(_DB_FILE, _DEFAULT_VEHICLES)
    return dict(_DEFAULT_VEHICLES)


def _write_json(path: Path, data) -> None:
    """Atomic write via temp file → rename."""
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
    except OSError as e:
        print(f"[DB] Warning: could not write {path.name}: {e}")


# ── History DB ────────────────────────────────────────────────────────────────
def _load_history() -> list:
    if _HISTORY_FILE.exists():
        try:
            with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[DB] Warning: history.json corrupted ({e}), starting fresh.")
    return []


# ── Live in-memory stores ─────────────────────────────────────────────────────
VEHICLE_DB: dict[str, dict] = _load_db()
HISTORY_DB: list[dict]      = _load_history()


# ── Public save helpers ───────────────────────────────────────────────────────
def save_vehicle_db() -> None:
    """Persist VEHICLE_DB to disk. Call after every mutation."""
    _write_json(_DB_FILE, VEHICLE_DB)


def save_history_db() -> None:
    """Persist HISTORY_DB to disk. Call after every new completed session."""
    _write_json(_HISTORY_FILE, HISTORY_DB)


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
    # Fallback: cek timestamp in-memory
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
    """Set exit_approved=True untuk session tamu. Return False kalau session tidak ada."""
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
    """Flag session sebagai perlu bayar manual."""
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
    """Return semua session aktif — untuk admin panel."""
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


async def close_session(plate: str) -> Optional[dict]:
    key = f"session:{_normalize(plate)}"
    redis = await get_redis()
    session = await get_active_session(plate)
    if not session:
        return None

    duration_secs  = time.time() - session["entry_ts"]
    duration_hours = max(1, int(duration_secs / 3600) + (1 if duration_secs % 3600 > 0 else 0))

    k       = _normalize(plate)
    vehicle = VEHICLE_DB.get(k, {})
    vtype   = vehicle.get("vehicle_type", "motor")
    fee     = (
        min(1000 + (duration_hours - 1) * 1000, 2000)
        if vtype == "motor"
        else min(2000 + (duration_hours - 1) * 1000, 10000)
    )

    payment_method = "manual"
    paid_provider  = None
    ewallets       = vehicle.get("ewallets", [])

    for ew in sorted(ewallets, key=lambda x: (not x["is_primary"])):
        if ew["balance"] >= fee:
            ew["balance"] -= fee
            payment_method = "autodebit"
            paid_provider  = ew["provider"]
            break

    if payment_method == "autodebit":
        save_vehicle_db()

    session.update({
        "exit_time":      datetime.now(timezone.utc).isoformat(),
        "duration_secs":  int(duration_secs),
        "duration_hours": duration_hours,
        "fee":            fee,
        "payment_method": payment_method,
        "paid_provider":  paid_provider,
        "gate_location":  session.get("gate_location", gate_location(session.get("gate_id", ""))),
        "status":         "completed",
    })

    HISTORY_DB.append(session)
    save_history_db()

    if redis:
        await redis.delete(key)
    else:
        _mem_sessions.pop(key, None)

    return session

async def lookup_vehicle(plate: str) -> Optional[dict]:
    return VEHICLE_DB.get(_normalize(plate))