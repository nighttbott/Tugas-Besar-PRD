"""
core/security.py
Auth untuk tiga client:
  1. ANPR script      → X-ANPR-KEY header (shared secret)
  2. ESP32 firmware   → ?device_key=xxx query param
  3. Dashboard/Admin  → Bearer JWT (dev-login atau manual)
"""
import json
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from .config import get_settings, Settings

_bearer_scheme = HTTPBearer(auto_error=True)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def verify_esp32_device_key(device_key: str, settings: Settings) -> bool:
    try:
        keys: dict = json.loads(settings.ESP32_DEVICE_KEYS)
    except Exception:
        return False
    print(f"[DEBUG] device_key received: {repr(device_key)}")
    print(f"[DEBUG] known keys: {list(keys.values())}")
    print(f"[DEBUG] match: {device_key in keys.values()}")
    return device_key in keys.values()

def _decode_token(token: str, settings: Settings) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_jwt(sub: str, extra: dict, ttl_hours: float, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "iss": "itb-parking-backend", "iat": now,
               "exp": now + timedelta(hours=ttl_hours), **extra}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ── ANPR: shared secret via header ───────────────────────────────────────────

def require_anpr_key(
    x_anpr_key: Annotated[str | None, Header(alias="X-ANPR-KEY")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not x_anpr_key or x_anpr_key != settings.ANPR_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or missing X-ANPR-KEY.")


# ── ESP32: device_key query param ─────────────────────────────────────────────

def verify_esp32_device_key(device_key: str, settings: Settings) -> bool:
    try:
        keys: dict = json.loads(settings.ESP32_DEVICE_KEYS)
    except Exception:
        return False
    return device_key in keys.values()


# ── Dashboard JWT ─────────────────────────────────────────────────────────────

def require_dashboard_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    settings: Settings = Depends(get_settings),
) -> dict:
    payload = _decode_token(credentials.credentials, settings)
    if payload.get("sub") not in {"dashboard_user", "parking_admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Forbidden: insufficient permission.")
    return payload


def require_admin_token(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    settings: Settings = Depends(get_settings),
) -> dict:
    payload = _decode_token(credentials.credentials, settings)
    if payload.get("sub") != "parking_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Forbidden: admin access required.")
    return payload