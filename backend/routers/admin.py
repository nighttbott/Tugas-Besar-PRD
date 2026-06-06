"""
routers/admin.py
Admin-only endpoints.

Routes:
  POST /api/v1/admin/auth/token              → login
  GET  /api/v1/admin/vehicles                → list semua kendaraan
  PATCH /api/v1/admin/vehicles/{plate}/plate → ubah plat nomor
  GET  /api/v1/admin/sessions                → session aktif + tamu
  POST /api/v1/admin/sessions/{plate}/approve-exit → izinkan tamu keluar
  POST /api/v1/admin/vehicles/{plate}/transfer → transfer kendaraan
"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.config import get_settings, Settings
from core.database import (
    get_active_session, _normalize,
    approve_guest_exit, get_all_active_sessions,
)
from core.database_sql import get_db
from models.domain import Vehicle, EWallet
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
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Username atau password salah.")
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
    db: AsyncSession = Depends(get_db)
) -> list[dict]:
    query = select(Vehicle).options(selectinload(Vehicle.ewallets))
    db_result = await db.execute(query)
    vehicles = db_result.scalars().all()
    
    result = []
    for v in vehicles:
        session = await get_active_session(v.plate_normalized)
        ewallets_data = [{"provider": e.provider, "balance": e.balance, "masked_account": e.masked_account, "is_primary": e.is_primary} for e in v.ewallets]
        
        result.append({
            "plate_normalized":     v.plate_normalized,
            "plate_raw":            v.plate_raw,
            "nim":                  v.nim,
            "owner":                v.owner,
            "vehicle_type":         v.vehicle_type,
            "model":                v.model,
            "status":               v.status,
            "verification_status":  v.verification_status,
            "verified_at":          v.verified_at.isoformat() if v.verified_at else None,
            "verified_gate":        None, # We can query history if we need this, but for now None is ok
            "flag_reason":          None,
            "ewallets":             ewallets_data,
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
    db: AsyncSession = Depends(get_db)
) -> dict:
    import re
    old_key = _normalize(plate)
    new_key = req.new_plate

    query_old = select(Vehicle).where(Vehicle.plate_normalized == old_key)
    result_old = await db.execute(query_old)
    vehicle = result_old.scalar_one_or_none()

    if not vehicle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kendaraan tidak ditemukan.")
        
    if new_key != old_key:
        query_new = select(Vehicle).where(Vehicle.plate_normalized == new_key)
        result_new = await db.execute(query_new)
        if result_new.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Plat {new_key} sudah terdaftar.")

    session = await get_active_session(old_key)
    if session:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Kendaraan sedang parkir.")

    m = re.match(r"^([A-Z]{1,2})(\d{1,4})([A-Z]{1,3})$", new_key)
    new_plate_raw = f"{m.group(1)} {m.group(2)} {m.group(3)}" if m else new_key

    # Because changing a primary key in SQLAlchemy requires cascade updates 
    # (if relying on db cascade) or cloning and deleting, let's clone.
    new_vehicle = Vehicle(
        plate_normalized=new_key,
        plate_raw=new_plate_raw,
        nim=vehicle.nim,
        owner=vehicle.owner,
        vehicle_type=vehicle.vehicle_type,
        model=vehicle.model,
        status="active",
        anpr_verified=vehicle.anpr_verified,
        verification_status=vehicle.verification_status,
        anpr_verified_at=vehicle.anpr_verified_at,
        anpr_verified_by=vehicle.anpr_verified_by,
    )
    
    db.add(new_vehicle)
    await db.delete(vehicle)
    await db.commit()

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
    db: AsyncSession = Depends(get_db)
) -> list[dict]:
    sessions = await get_all_active_sessions()
    
    # Batch query vehicles
    plates = [s.get("plate", "") for s in sessions if s.get("plate")]
    vehicles_dict = {}
    if plates:
        query = select(Vehicle).where(Vehicle.plate_normalized.in_(plates))
        result = await db.execute(query)
        for v in result.scalars().all():
            vehicles_dict[v.plate_normalized] = v

    result = []
    for s in sessions:
        plate   = s.get("plate", "")
        vehicle = vehicles_dict.get(plate)
        result.append({
            **s,
            "is_guest":      s.get("is_guest", False),
            "exit_approved": s.get("exit_approved", False),
            "owner":         vehicle.owner if vehicle else "Tamu",
            "model":         vehicle.model if vehicle else "–",
            "vehicle_type":  vehicle.vehicle_type if vehicle else "–",
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session tidak ditemukan.")
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
    db: AsyncSession = Depends(get_db)
) -> dict:
    key = _normalize(plate)
    
    query = select(Vehicle).where(Vehicle.plate_normalized == key).options(selectinload(Vehicle.ewallets))
    result = await db.execute(query)
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kendaraan tidak ditemukan.")

    session = await get_active_session(key)
    if session and not force:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Kendaraan sedang parkir. Tambah ?force=true untuk override.")

    is_parked = session is not None
    old_nim   = vehicle.nim
    old_owner = vehicle.owner

    vehicle.nim = req.new_nim
    vehicle.owner = req.new_owner
    
    # Delete all associated ewallets
    for ew in list(vehicle.ewallets):
        await db.delete(ew)

    if not is_parked:
        vehicle.verification_status = "pending"
        vehicle.verified_at = None
        vehicle.anpr_verified = False
        
    vehicle.status = "active"

    await db.commit()

    return {
        "message":     f"Kendaraan {vehicle.plate_raw} berhasil ditransfer.",
        "plate_raw":   vehicle.plate_raw,
        "old_nim":     old_nim,
        "old_owner":   old_owner,
        "new_nim":     req.new_nim,
        "new_owner":   req.new_owner,
        "note":        "Kendaraan perlu diverifikasi ulang saat masuk gate pertama kali.",
    }
