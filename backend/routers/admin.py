"""
routers/admin.py
Admin-only endpoints.

Routes:
  POST /api/v1/admin/auth/token              → login
  GET  /api/v1/admin/vehicles                → list semua kendaraan
  PATCH /api/v1/admin/vehicles/{plate}/plate → ubah plat nomor
  GET  /api/v1/admin/sessions                → session aktif + tamu
  POST /api/v1/admin/sessions/{plate}/approve-exit → izinkan tamu keluar
"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from core.config import get_settings, Settings
from core.database import (
    VEHICLE_DB, get_active_session, _normalize,
    save_vehicle_db, approve_guest_exit, get_all_active_sessions,
)
from core.security import require_admin_token, create_jwt

router = APIRouter()

ADMIN_USERS = {
    "admin":   "parkir2024",
    "petugas": "gerbang123",
}


# ── POST /api/v1/admin/auth/token ─────────────────────────────────────────────
class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=2)
    password: str = Field(..., min_length=4)


@router.post("/auth/token", summary="Admin login → JWT")
async def admin_login(
    req: AdminLoginRequest,
    settings: Settings = Depends(get_settings),
) -> dict:
    if ADMIN_USERS.get(req.username) != req.password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="Username atau password salah.")
    token = create_jwt(
        sub="parking_admin",
        extra={"admin_id": req.username},
        ttl_hours=8,
        settings=settings,
    )
    return {
        "access_token": token,
        "token_type":   "bearer",
        "admin_id":     req.username,
        "message":      f"Login berhasil sebagai {req.username}.",
    }


# ── GET /api/v1/admin/vehicles ────────────────────────────────────────────────
@router.get("/vehicles", summary="List all registered vehicles (admin)")
async def admin_list_vehicles(
    _: Annotated[dict, Depends(require_admin_token)],
) -> list[dict]:
    result = []
    for key, v in VEHICLE_DB.items():
        session = await get_active_session(key)
        result.append({
            "plate_normalized": key,
            "plate_raw":            v["plate_raw"],
            "nim":                  v.get("nim", ""),
            "owner":                v["owner"],
            "vehicle_type":         v["vehicle_type"],
            "model":                v["model"],
            "status":               v.get("status", "active"),
            "verification_status":  v.get("verification_status", "verified"),  # data lama = verified
            "verified_at":          v.get("verified_at"),
            "verified_gate":        v.get("verified_gate"),
            "flag_reason":          v.get("flag_reason"),
            "ewallets":             v.get("ewallets", []),
            "is_parked":            session is not None,
        })
    return result


# ── PATCH /api/v1/admin/vehicles/{plate}/plate ────────────────────────────────
class ChangePlateRequest(BaseModel):
    new_plate: str = Field(..., min_length=4, max_length=12)
    reason:    str = Field(default="")

    @field_validator("new_plate")
    @classmethod
    def validate_plate(cls, v: str) -> str:
        import re
        normalized = v.upper().replace(" ", "")
        if not re.match(r"^[A-Z]{1,2}\d{1,4}[A-Z]{1,3}$", normalized):
            raise ValueError("Format plat tidak valid.")
        return normalized


@router.patch("/vehicles/{plate}/plate", summary="Ubah plat nomor (admin only)")
async def admin_change_plate(
    plate: str,
    req: ChangePlateRequest,
    admin_payload: Annotated[dict, Depends(require_admin_token)],
) -> dict:
    import re
    old_key = _normalize(plate)
    new_key = req.new_plate

    if old_key not in VEHICLE_DB:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kendaraan tidak ditemukan.")
    if new_key in VEHICLE_DB and new_key != old_key:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail=f"Plat {new_key} sudah terdaftar.")

    session = await get_active_session(old_key)
    if session:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Kendaraan sedang parkir.")

    vehicle = dict(VEHICLE_DB[old_key])
    m = re.match(r"^([A-Z]{1,2})(\d{1,4})([A-Z]{1,3})$", new_key)
    new_plate_raw = f"{m.group(1)} {m.group(2)} {m.group(3)}" if m else new_key

    vehicle["plate_raw"]            = new_plate_raw
    vehicle["status"]               = "active"
    vehicle["plate_changed_by"]     = admin_payload.get("admin_id", "Admin")
    vehicle["plate_changed_at"]     = datetime.now(timezone.utc).isoformat()
    vehicle["plate_change_reason"]  = req.reason

    del VEHICLE_DB[old_key]
    VEHICLE_DB[new_key] = vehicle
    save_vehicle_db()

    return {
        "message":       f"Plat berhasil diubah ke {new_plate_raw}.",
        "old_plate":     old_key,
        "new_plate":     new_key,
        "new_plate_raw": new_plate_raw,
    }


# ── GET /api/v1/admin/sessions ────────────────────────────────────────────────
@router.get("/sessions", summary="List semua session aktif (admin)")
async def admin_list_sessions(
    _: Annotated[dict, Depends(require_admin_token)],
) -> list[dict]:
    sessions = await get_all_active_sessions()
    result = []
    for s in sessions:
        plate   = s.get("plate", "")
        vehicle = VEHICLE_DB.get(plate)
        result.append({
            **s,
            "is_guest":      s.get("is_guest", False),
            "exit_approved": s.get("exit_approved", False),
            "owner":         vehicle["owner"] if vehicle else "Tamu",
            "model":         vehicle["model"] if vehicle else "–",
            "vehicle_type":  vehicle["vehicle_type"] if vehicle else "–",
        })
    return result


# ── POST /api/v1/admin/sessions/{plate}/approve-exit ─────────────────────────
@router.post("/sessions/{plate}/approve-exit", summary="Izinkan keluar")
async def admin_approve_exit(
    plate: str,
    _: Annotated[dict, Depends(require_admin_token)],
) -> dict:
    ok = await approve_guest_exit(plate)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail="Session tidak ditemukan.")
    return {"message": f"Kendaraan {plate} diizinkan keluar.", "plate": plate}

# ── POST /api/v1/admin/vehicles/{plate}/transfer ──────────────────────────────
class TransferRequest(BaseModel):
    new_nim: str = Field(..., min_length=5, description="NIM pemilik baru")
    new_owner: str = Field(..., min_length=2, description="Nama pemilik baru")
    reason: str = Field(default="", description="Alasan transfer")


@router.post("/vehicles/{plate}/transfer", summary="Transfer kepemilikan kendaraan (admin)")
async def admin_transfer_vehicle(
    plate: str,
    req: TransferRequest,
    admin_payload: Annotated[dict, Depends(require_admin_token)],
    force: bool = False,
) -> dict:
    key = _normalize(plate)
    if key not in VEHICLE_DB:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kendaraan tidak ditemukan.")

    session = await get_active_session(key)
    if session and not force:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Kendaraan sedang parkir. Tambah ?force=true untuk override.")

    is_parked = session is not None  # simpan status parkir
    vehicle = VEHICLE_DB[key]
    old_nim   = vehicle.get("nim", "–")
    old_owner = vehicle.get("owner", "–")

    # Reset ke pending — harus verify ulang via gate
    vehicle["nim"]                      = req.new_nim
    vehicle["owner"]                    = req.new_owner
    vehicle["ewallets"]                 = []
    if not is_parked:  # session sudah dicek di atas — None kalau tidak parkir
        vehicle["verification_status"]      = "pending"
        vehicle["verified_at"]              = None
        vehicle["verified_gate"]            = None
        vehicle["verification_confidence"]  = None
    vehicle["flag_reason"]              = None
    vehicle["status"]                   = "active"
    vehicle["transferred_by"]           = admin_payload.get("admin_id", "Admin")
    vehicle["transferred_at"]           = datetime.now(timezone.utc).isoformat()
    vehicle["transfer_reason"]          = req.reason
    vehicle["previous_owner"]           = f"{old_owner} (NIM: {old_nim})"

    save_vehicle_db()

    return {
        "message":     f"Kendaraan {vehicle['plate_raw']} berhasil ditransfer.",
        "plate_raw":   vehicle["plate_raw"],
        "old_nim":     old_nim,
        "old_owner":   old_owner,
        "new_nim":     req.new_nim,
        "new_owner":   req.new_owner,
        "note":        "Kendaraan perlu diverifikasi ulang saat masuk gate pertama kali.",
    }