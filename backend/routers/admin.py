"""
routers/admin.py
Admin-only endpoints. All require sub="parking_admin" JWT.

Routes:
  GET  /api/v1/admin/vehicles          → list ALL vehicles (any NIM)
  POST /api/v1/admin/vehicles/{plate}/verify-anpr  → verify ANPR
  POST /api/v1/admin/vehicles/{plate}/unverify-anpr → revoke verification
  POST /api/v1/admin/auth/token        → login with username+password → JWT
"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from core.config import get_settings, Settings
from core.database import VEHICLE_DB, get_active_session, _normalize, save_vehicle_db
from core.security import require_admin_token, create_admin_token

router = APIRouter()

# ── Hardcoded admin credentials (replace with DB in production) ───────────────
ADMIN_USERS = {
    "admin": "parkir2024",        # username: password
    "petugas": "gerbang123",
}


# ── POST /api/v1/admin/auth/token — Admin login ───────────────────────────────
class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=2)
    password: str = Field(..., min_length=4)


@router.post("/auth/token", summary="Admin login → JWT")
async def admin_login(
    req: AdminLoginRequest,
    settings: Settings = Depends(get_settings),
) -> dict:
    if ADMIN_USERS.get(req.username) != req.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah.",
        )
    token = create_admin_token(req.username, settings)
    return {
        "access_token": token,
        "token_type":   "bearer",
        "admin_id":     req.username,
        "message":      f"Login berhasil sebagai {req.username}.",
    }


# ── GET /api/v1/admin/vehicles — List all vehicles ───────────────────────────
@router.get("/vehicles", summary="List all registered vehicles (admin)")
async def admin_list_vehicles(
    _: Annotated[dict, Depends(require_admin_token)],
) -> list[dict]:
    result = []
    for key, v in VEHICLE_DB.items():
        session = await get_active_session(key)
        ewallets = v.get("ewallets", [])
        result.append({
            "plate_normalized": key,
            "plate_raw":        v["plate_raw"],
            "nim":              v["nim"],
            "owner":            v["owner"],
            "vehicle_type":     v["vehicle_type"],
            "model":            v["model"],
            "status":           v["status"],
            "anpr_verified":    v["anpr_verified"],
            "ewallets":         ewallets,
            "is_parked":        session is not None,
        })
    return result


# ── POST /api/v1/admin/vehicles/{plate}/verify-anpr ──────────────────────────
class VerifyRequest(BaseModel):
    verified_by: str = Field(default="Admin Parkir")
    notes:       str = Field(default="")


@router.post("/vehicles/{plate}/verify-anpr", summary="Verify ANPR (admin only)")
async def admin_verify_anpr(
    plate: str,
    req: VerifyRequest,
    admin_payload: Annotated[dict, Depends(require_admin_token)],
) -> dict:
    key = _normalize(plate)
    if key not in VEHICLE_DB:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kendaraan tidak ditemukan.")

    vehicle = VEHICLE_DB[key]
    vehicle["anpr_verified"]    = True
    vehicle["anpr_verified_by"] = req.verified_by or admin_payload.get("admin_id", "Admin")
    vehicle["anpr_verified_at"] = datetime.now(timezone.utc).isoformat()
    vehicle["anpr_notes"]       = req.notes

    # Auto-activate when ANPR verified
    if vehicle["status"] == "inactive":
        vehicle["status"] = "active"

    save_vehicle_db()

    return {
        "message":       f"ANPR {vehicle['plate_raw']} berhasil diverifikasi.",
        "plate_raw":     vehicle["plate_raw"],
        "anpr_verified": True,
        "status":        vehicle["status"],
        "verified_by":   vehicle["anpr_verified_by"],
        "verified_at":   vehicle["anpr_verified_at"],
    }


# ── POST /api/v1/admin/vehicles/{plate}/unverify-anpr ────────────────────────
@router.post("/vehicles/{plate}/unverify-anpr", summary="Revoke ANPR verification (admin only)")
async def admin_unverify_anpr(
    plate: str,
    _: Annotated[dict, Depends(require_admin_token)],
) -> dict:
    key = _normalize(plate)
    if key not in VEHICLE_DB:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kendaraan tidak ditemukan.")

    vehicle = VEHICLE_DB[key]
    vehicle["anpr_verified"]    = False
    vehicle["anpr_verified_by"] = None
    vehicle["anpr_verified_at"] = None
    vehicle["status"]           = "inactive"

    save_vehicle_db()

    return {
        "message":       f"Verifikasi ANPR {vehicle['plate_raw']} dicabut.",
        "plate_raw":     vehicle["plate_raw"],
        "anpr_verified": False,
        "status":        "inactive",
    }


# ── PATCH /api/v1/admin/vehicles/{plate}/plate ────────────────────────────────
class ChangePlateRequest(BaseModel):
    new_plate: str = Field(..., min_length=4, max_length=12,
                           description="Plat nomor baru (normalized, no spaces)")
    reason: str = Field(default="", description="Alasan perubahan plat")

    @field_validator("new_plate")
    @classmethod
    def validate_plate(cls, v: str) -> str:
        import re
        normalized = v.upper().replace(" ", "")
        if not re.match(r"^[A-Z]{1,2}\d{1,4}[A-Z]{1,3}$", normalized):
            raise ValueError("Format plat tidak valid. Contoh: B 1234 ABC, D 4321 ITB")
        return normalized


@router.patch("/vehicles/{plate}/plate", summary="Change vehicle plate number (admin only)")
async def admin_change_plate(
    plate: str,
    req: ChangePlateRequest,
    admin_payload: Annotated[dict, Depends(require_admin_token)],
) -> dict:
    """
    Admin-only: change a vehicle's plate number.
    - Old plate entry is removed from VEHICLE_DB
    - New plate entry is created with the same vehicle data
    - anpr_verified is reset to False (requires re-verification with new STNK)
    - status is reset to "inactive"
    - Persists to db.json immediately
    """
    from core.database import VEHICLE_DB, save_vehicle_db, _normalize

    old_key = _normalize(plate)
    new_key = req.new_plate  # Already normalized by validator

    if old_key not in VEHICLE_DB:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kendaraan tidak ditemukan.")

    if new_key in VEHICLE_DB and new_key != old_key:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Plat {new_key} sudah terdaftar di sistem.",
        )

    # Check if vehicle is currently parked
    session = await get_active_session(old_key)
    if session:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Kendaraan sedang parkir. Tidak dapat mengubah plat nomor.",
        )

    # Copy vehicle data to new key
    vehicle = dict(VEHICLE_DB[old_key])

    # Format new plate for display
    import re
    m = re.match(r"^([A-Z]{1,2})(\d{1,4})([A-Z]{1,3})$", new_key)
    new_plate_raw = f"{m.group(1)} {m.group(2)} {m.group(3)}" if m else new_key

    vehicle["plate_raw"]     = new_plate_raw
    vehicle["anpr_verified"] = False   # Must re-verify with new STNK
    vehicle["status"]        = "inactive"
    vehicle["plate_changed_by"] = admin_payload.get("admin_id", "Admin")
    vehicle["plate_changed_at"] = datetime.now(timezone.utc).isoformat()
    vehicle["plate_change_reason"] = req.reason

    # Remove old, insert new
    del VEHICLE_DB[old_key]
    VEHICLE_DB[new_key] = vehicle
    save_vehicle_db()

    return {
        "message":         f"Plat nomor berhasil diubah dari {VEHICLE_DB.get(old_key, {}).get('plate_raw', old_key)} ke {new_plate_raw}.",
        "old_plate":       old_key,
        "new_plate":       new_key,
        "new_plate_raw":   new_plate_raw,
        "anpr_verified":   False,
        "status":          "inactive",
        "note":            "Kendaraan perlu diverifikasi ulang ANPR dengan STNK baru.",
    }
