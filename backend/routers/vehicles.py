"""
routers/vehicles.py — Full vehicle CRUD + e-wallet management + ANPR verification.
Refactored to use SQLAlchemy Asynchronous Sessions.
"""
import re
import time
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from core.security import create_jwt, require_dashboard_token
from core.config import get_settings, Settings
from core.database import (
    SUPPORTED_EWALLETS,
    get_active_session, 
    _normalize,
)
from core.database_sql import get_db
from models.domain import Vehicle, EWallet, History

router = APIRouter()

PLATE_RE = re.compile(r"^[A-Z]{1,2}\s?\d{1,4}\s?[A-Z]{1,3}$")

def fmt_plate(normalized: str) -> str:
    m = re.match(r"^([A-Z]{1,2})(\d{1,4})([A-Z]{1,3})$", normalized)
    return f"{m.group(1)} {m.group(2)} {m.group(3)}" if m else normalized


# ── Schemas ───────────────────────────────────────────────────────────────────

class AddVehicleRequest(BaseModel):
    plate_number:  str = Field(..., min_length=3, max_length=12)
    vehicle_type:  Literal["motor", "mobil"]
    model:         str = Field(..., min_length=2, max_length=60)
    nim:           str = Field(default="2021184750")

    @field_validator("plate_number")
    @classmethod
    def validate_plate(cls, v: str) -> str:
        c = v.strip().upper()
        if not PLATE_RE.match(c):
            raise ValueError("Format plat tidak valid. Contoh: B 1234 ABC, D 4321 ITB")
        return _normalize(c)


class AddEwalletRequest(BaseModel):
    provider:        str = Field(..., description="GoPay | OVO | ShopeePay | Dana | LinkAja")
    masked_account:  str = Field(default="", max_length=20)
    initial_balance: int = Field(default=100000, ge=0, le=100_000_000)
    set_as_primary:  bool = Field(default=False)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in SUPPORTED_EWALLETS:
            raise ValueError(f"Provider tidak valid. Pilihan: {', '.join(SUPPORTED_EWALLETS)}")
        return v


class UpdateBalanceRequest(BaseModel):
    balance: int = Field(..., ge=0, le=100_000_000, description="Saldo baru dalam IDR")


class EditModelRequest(BaseModel):
    model: str = Field(..., min_length=2, max_length=60)


class VerifyAnprRequest(BaseModel):
    verified_by: str = Field(default="Petugas Parkir")


class UserLoginRequest(BaseModel):
    nim:      str = Field(..., min_length=5)
    password: str = Field(..., min_length=4)


# ── Hardcoded user credentials (demo) ────────────────────────────────────────
USER_DB = {
    "13525001": {"password": "mahasiswa1", "name": "Michael Abduh"},
    "13525002": {"password": "mahasiswa2", "name": "Danesh Zacky"},
    "13525003": {"password": "mahasiswa3", "name": "Naufal Salastra"},
}


@router.post("/auth/login", summary="User login → JWT")
async def user_login(
    req: UserLoginRequest,
    settings: Settings = Depends(get_settings),
) -> dict:
    user = USER_DB.get(req.nim)
    if not user or user["password"] != req.password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            detail="NIM atau password salah.")
    token = create_jwt(
        sub="dashboard_user",
        extra={"nim": req.nim, "name": user["name"]},
        ttl_hours=8,
        settings=settings,
    )
    return {
        "access_token": token,
        "token_type":   "bearer",
        "nim":          req.nim,
        "name":         user["name"],
    }


# ── GET /api/v1/vehicles/ ─────────────────────────────────────────────────────
@router.get("/", summary="List all vehicles for NIM")
async def list_vehicles(
    token_payload: Annotated[dict, Depends(require_dashboard_token)],
    db: AsyncSession = Depends(get_db)
) -> list[dict]:
    nim = token_payload.get("nim", "")
    
    query = select(Vehicle).where(Vehicle.nim == nim).options(selectinload(Vehicle.ewallets))
    result = await db.execute(query)
    vehicles = result.scalars().all()
    
    response = []
    for v in vehicles:
        session = await get_active_session(v.plate_normalized)
        
        ewallets_data = []
        primary_ewallet = None
        backup_ewallet = None
        
        for ew in sorted(v.ewallets, key=lambda e: (not e.is_primary, e.id)):
            ew_dict = {
                "provider": ew.provider,
                "balance": ew.balance,
                "masked_account": ew.masked_account,
                "is_primary": ew.is_primary
            }
            ewallets_data.append(ew_dict)
            if ew.is_primary and primary_ewallet is None:
                primary_ewallet = ew_dict
            elif backup_ewallet is None:
                backup_ewallet = ew_dict
                
        if not primary_ewallet and ewallets_data:
            primary_ewallet = ewallets_data[0]
            
        response.append({
            "plate_normalized": v.plate_normalized,
            "plate_raw":        v.plate_raw,
            "nim":              v.nim,
            "owner":            v.owner,
            "vehicle_type":     v.vehicle_type,
            "model":            v.model,
            "status":           v.status,
            "ewallets":         ewallets_data,
            "primary_ewallet":  primary_ewallet,
            "backup_ewallet":   backup_ewallet,
            "is_parked":        session is not None,
            "active_session":   session,
            "anpr_verified":    v.anpr_verified,
            "verification_status": v.verification_status,
            "flag_reason":      None,
        })
    return response


# ── POST /api/v1/vehicles/ ────────────────────────────────────────────────────
@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_vehicle(
    req: AddVehicleRequest,
    token_payload: Annotated[dict, Depends(require_dashboard_token)],
    db: AsyncSession = Depends(get_db)
) -> dict:
    nim   = token_payload.get("nim", req.nim)
    owner = token_payload.get("name") or token_payload.get("nim", "User")
    plate_normalized = req.plate_number
    plate_raw = fmt_plate(plate_normalized)

    try:
        query = select(Vehicle).where(Vehicle.plate_normalized == plate_normalized)
        result = await db.execute(query)
        existing_vehicle = result.scalar_one_or_none()

        if existing_vehicle:
            if existing_vehicle.nim == nim:
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    detail=f"Plat {plate_raw} sudah terdaftar di akun Anda.")
            else:
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    detail=f"Plat {plate_raw} sudah terdaftar oleh pengguna lain. "
                                           f"Jika ini kendaraan Anda, hubungi admin untuk transfer kepemilikan.")

        new_vehicle = Vehicle(
            plate_normalized=plate_normalized,
            plate_raw=plate_raw,
            nim=nim,
            owner=owner,
            vehicle_type=req.vehicle_type,
            model=req.model,
            status="inactive",
            verification_status="pending",
        )

        db.add(new_vehicle)
        await db.commit()
        await db.refresh(new_vehicle)
        
        return {"message": f"Kendaraan {plate_raw} berhasil didaftarkan.", "plate_raw": plate_raw}

    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Gagal menyimpan data kendaraan, identitas duplikat.")
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Terjadi kesalahan pada server database.")


# ── DELETE /api/v1/vehicles/{plate} ──────────────────────────────────────────
@router.delete("/{plate}")
async def delete_vehicle(
    plate: str,
    _: Annotated[dict, Depends(require_dashboard_token)] = None,
    db: AsyncSession = Depends(get_db)
) -> dict:
    key = _normalize(plate)
    
    query = select(Vehicle).where(Vehicle.plate_normalized == key)
    result = await db.execute(query)
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Plat {fmt_plate(key)} tidak ditemukan.")
        
    if await get_active_session(key):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Kendaraan sedang parkir, tidak bisa dihapus.")
        
    await db.delete(vehicle)
    await db.commit()
    return {"message": f"Kendaraan {fmt_plate(key)} berhasil dihapus."}


# ── GET /api/v1/vehicles/sessions ────────────────────────────────────────────
@router.get("/sessions")
async def get_sessions_stats(
    token_payload: Annotated[dict, Depends(require_dashboard_token)],
    db: AsyncSession = Depends(get_db)
) -> dict:
    nim = token_payload.get("nim", "")
    
    query = select(Vehicle).where(Vehicle.nim == nim).options(selectinload(Vehicle.ewallets))
    result = await db.execute(query)
    user_vehicles = result.scalars().all()
    
    active_sessions = []
    user_plates = set()
    
    for vehicle in user_vehicles:
        user_plates.add(vehicle.plate_normalized)
        session = await get_active_session(vehicle.plate_normalized)
        if not session:
            continue
            
        elapsed  = int(time.time() - session.get("entry_ts", time.time()))
        jam      = max(1, (elapsed // 3600) + (1 if elapsed % 3600 > 0 else 0))
        vtype    = vehicle.vehicle_type
        est_fee  = min(1000 + (jam-1)*1000, 2000) if vtype == "motor" else min(2000 + (jam-1)*1000, 10000)
        h, m     = elapsed // 3600, (elapsed % 3600) // 60
        
        primary = next(({"provider": e.provider, "balance": e.balance, "masked_account": e.masked_account, "is_primary": e.is_primary} 
                        for e in vehicle.ewallets if e.is_primary), None)
        if not primary and vehicle.ewallets:
            e = vehicle.ewallets[0]
            primary = {"provider": e.provider, "balance": e.balance, "masked_account": e.masked_account, "is_primary": e.is_primary}
            
        active_sessions.append({
            "plate_normalized": vehicle.plate_normalized,
            "plate_raw":        vehicle.plate_raw,
            "model":            vehicle.model,
            "vehicle_type":     vtype,
            "gate_id":          session.get("gate_id", "G1"),
            "entry_time":       session.get("entry_time", ""),
            "entry_ts":         session.get("entry_ts", 0),
            "elapsed_secs":     elapsed,
            "duration_label":   f"{h}j {m}m",
            "est_fee":          est_fee,
            "est_fee_label":    f"Rp{est_fee:,}".replace(",", "."),
            "primary_ewallet":  primary,
        })

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_done_count = 0
    if user_plates:
        hist_query = select(func.count(History.id)).where(
            History.plate_normalized.in_(user_plates),
            History.entry_time >= today_start
        )
        hist_result = await db.execute(hist_query)
        today_done_count = hist_result.scalar() or 0

    return {
        "total_vehicles":   len(user_vehicles),
        "active_sessions":  active_sessions,
        "active_count":     len(active_sessions),
        "today_completed":  today_done_count,
    }


# ── POST /api/v1/vehicles/{plate}/ewallet ────────────────────────────────────
@router.post("/{plate}/ewallet", status_code=status.HTTP_201_CREATED)
async def add_ewallet(
    plate: str,
    req: AddEwalletRequest,
    _: Annotated[dict, Depends(require_dashboard_token)] = None,
    db: AsyncSession = Depends(get_db)
) -> dict:
    key = _normalize(plate)
    query = select(Vehicle).where(Vehicle.plate_normalized == key).options(selectinload(Vehicle.ewallets))
    result = await db.execute(query)
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kendaraan tidak ditemukan.")
        
    if any(e.provider == req.provider for e in vehicle.ewallets):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"{req.provider} sudah terhubung ke kendaraan ini.")

    is_primary = req.set_as_primary or len(vehicle.ewallets) == 0
    
    if is_primary:
        for e in vehicle.ewallets:
            e.is_primary = False
            
    new_ew = EWallet(
        plate_normalized=key,
        provider=req.provider,
        balance=req.initial_balance,
        masked_account=req.masked_account or f"08xx-xxxx-xxxx",
        is_primary=is_primary
    )
    db.add(new_ew)
    
    if vehicle.status == "inactive" and vehicle.anpr_verified:
        vehicle.status = "active"
        
    await db.commit()
    await db.refresh(new_ew)
    
    return {"message": f"{req.provider} berhasil dihubungkan.", "ewallet": {"provider": new_ew.provider, "balance": new_ew.balance, "masked_account": new_ew.masked_account, "is_primary": new_ew.is_primary}}


# ── PUT /api/v1/vehicles/{plate}/ewallet/{provider}/balance ──────────────────
@router.put("/{plate}/ewallet/{provider}/balance")
async def update_balance(
    plate: str,
    provider: str,
    req: UpdateBalanceRequest,
    _: Annotated[dict, Depends(require_dashboard_token)] = None,
    db: AsyncSession = Depends(get_db)
) -> dict:
    key = _normalize(plate)
    query = select(EWallet).where(EWallet.plate_normalized == key, EWallet.provider == provider)
    result = await db.execute(query)
    ew = result.scalar_one_or_none()
    
    if not ew:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{provider} tidak terhubung.")
        
    ew.balance = req.balance
    await db.commit()
    return {"message": f"Saldo {provider} diperbarui.", "balance": req.balance}


# ── DELETE /api/v1/vehicles/{plate}/ewallet/{provider} ───────────────────────
@router.delete("/{plate}/ewallet/{provider}")
async def remove_ewallet(
    plate: str,
    provider: str,
    _: Annotated[dict, Depends(require_dashboard_token)] = None,
    db: AsyncSession = Depends(get_db)
) -> dict:
    key = _normalize(plate)
    query = select(Vehicle).where(Vehicle.plate_normalized == key).options(selectinload(Vehicle.ewallets))
    result = await db.execute(query)
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kendaraan tidak ditemukan.")
        
    removed_ew = next((e for e in vehicle.ewallets if e.provider == provider), None)
    if not removed_ew:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{provider} tidak ditemukan.")
        
    was_primary = removed_ew.is_primary
    await db.delete(removed_ew)
    vehicle.ewallets.remove(removed_ew)
    
    if was_primary and len(vehicle.ewallets) > 0:
        vehicle.ewallets[0].is_primary = True
        
    await db.commit()
    return {"message": f"{provider} berhasil dihapus."}


# ── PUT /api/v1/vehicles/{plate}/ewallet/{provider}/primary ──────────────────
@router.put("/{plate}/ewallet/{provider}/primary")
async def set_primary_ewallet(
    plate: str,
    provider: str,
    _: Annotated[dict, Depends(require_dashboard_token)] = None,
    db: AsyncSession = Depends(get_db)
) -> dict:
    key = _normalize(plate)
    query = select(EWallet).where(EWallet.plate_normalized == key)
    result = await db.execute(query)
    ewallets = result.scalars().all()
    
    if not ewallets:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kendaraan tidak ditemukan atau tidak memiliki e-wallet.")
        
    found = False
    for e in ewallets:
        if e.provider == provider:
            e.is_primary = True
            found = True
        else:
            e.is_primary = False
            
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{provider} tidak ditemukan.")
        
    await db.commit()
    return {"message": f"{provider} dijadikan e-wallet primer."}


# ── PATCH /api/v1/vehicles/{plate}/model ─────────────────────────────────────
@router.patch("/{plate}/model", summary="Edit vehicle model name (user)")
async def edit_model(
    plate: str,
    req: EditModelRequest,
    _: Annotated[dict, Depends(require_dashboard_token)] = None,
    db: AsyncSession = Depends(get_db)
) -> dict:
    key = _normalize(plate)
    query = select(Vehicle).where(Vehicle.plate_normalized == key)
    result = await db.execute(query)
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kendaraan tidak ditemukan.")

    old_model = vehicle.model
    vehicle.model = req.model.strip()
    await db.commit()

    return {
        "message":   "Model kendaraan berhasil diperbarui.",
        "plate_raw": vehicle.plate_raw,
        "old_model": old_model,
        "new_model": vehicle.model,
    }


# ── PUT /api/v1/vehicles/{plate}/verify ──────────────────────────────────────
@router.put("/{plate}/verify", summary="Verify ANPR for a vehicle (petugas only)")
async def verify_anpr(
    plate: str,
    req: VerifyAnprRequest,
    _: Annotated[dict, Depends(require_dashboard_token)] = None,
    db: AsyncSession = Depends(get_db)
) -> dict:
    key = _normalize(plate)
    query = select(Vehicle).where(Vehicle.plate_normalized == key).options(selectinload(Vehicle.ewallets))
    result = await db.execute(query)
    vehicle = result.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kendaraan tidak ditemukan.")

    vehicle.anpr_verified = True
    vehicle.anpr_verified_by = req.verified_by
    vehicle.anpr_verified_at = datetime.now(timezone.utc)

    if len(vehicle.ewallets) > 0:
        vehicle.status = "active"

    await db.commit()

    return {
        "message":       f"Kendaraan {vehicle.plate_raw} berhasil diverifikasi oleh {req.verified_by}.",
        "plate_raw":     vehicle.plate_raw,
        "anpr_verified": True,
        "status":        vehicle.status,
    }
