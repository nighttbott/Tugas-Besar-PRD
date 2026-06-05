"""
services/gate_service.py
Core business logic for gate trigger decisions.
Separated from the router so it can be unit-tested independently.

Decision tree for entry:
  1. Confidence < 85%         → deny (low_confidence)
  2. Plate in cooldown window → skip (cooldown)
  3. Plate not registered     → deny (unregistered)
  4. Vehicle status blocked   → deny (blocked)
  5. Already has active session (duplicate entry) → deny (already_inside)
  6. All checks pass          → open_gate, create session, send WS command

Decision tree for exit:
  1. No active session found  → deny (no_active_session)
  2. Pass                     → open_gate, close session, charge billing
"""
import logging
from datetime import datetime, timezone
import time

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from core.database import (
    check_cooldown,
    set_cooldown,
    get_active_session,
    create_session,
    delete_active_session,
    flag_manual_payment,
    gate_location,
    _normalize,
)
from models.gate import GateTriggerRequest, GateTriggerResponse
from models.domain import Vehicle, History, EWallet
from services.ws_manager import ws_manager

from core.mqtt_manager import mqtt_manager

logger = logging.getLogger("gate_service")

CONFIDENCE_THRESHOLD = 0.75

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

async def process_gate_trigger(req: GateTriggerRequest, db: AsyncSession) -> GateTriggerResponse:
    plate = _normalize(req.plate_number)
    ts = _now_iso()

    # ── 1. Confidence gate ────────────────────────────────────────────────────
    if req.confidence < CONFIDENCE_THRESHOLD:
        logger.warning("[%s] Low confidence %.2f — access denied.", plate, req.confidence)
        return GateTriggerResponse(
            action="low_confidence",
            plate_number=plate,
            gate_id=req.gate_id,
            reason=f"ANPR confidence {req.confidence:.0%} below threshold.",
            timestamp=ts,
        )

    # ── 2. Cooldown check ─────────────────────────────────────────────────────
    if await check_cooldown(plate):
        logger.info("[%s] In cooldown window — skipping.", plate)
        return GateTriggerResponse(
            action="cooldown",
            plate_number=plate,
            gate_id=req.gate_id,
            reason="Duplicate trigger within cooldown window.",
            timestamp=ts,
        )

    # ── 3. Database lookup ────────────────────────────────────────────────────
    query = select(Vehicle).where(Vehicle.plate_normalized == plate).options(selectinload(Vehicle.ewallets))
    result = await db.execute(query)
    vehicle = result.scalar_one_or_none()

    # ── 4. Blocked check (hanya untuk kendaraan terdaftar) ───────────────────
    if vehicle and vehicle.status == "blocked":
        logger.warning("[%s] Vehicle is blocked.", plate)
        await set_cooldown(plate)
        return GateTriggerResponse(
            action="deny_access",
            plate_number=plate,
            gate_id=req.gate_id,
            reason="Akses kendaraan diblokir. Hubungi keamanan kampus.",
            timestamp=ts,
        )

    # ── ENTRY flow ─────────────────────────────────────────────────────────────
    if req.direction == "entry":
        # Cek duplicate session
        existing_session = await get_active_session(plate)
        if existing_session:
            logger.warning("[%s] Already has active session.", plate)
            await set_cooldown(plate)
            return GateTriggerResponse(
                action="deny_access",
                plate_number=plate,
                gate_id=req.gate_id,
                reason="Kendaraan sudah memiliki sesi aktif.",
                timestamp=ts,
            )

        session = await create_session(plate, req.gate_id, req.confidence, is_guest=vehicle is None)
        await set_cooldown(plate)

        # Auto-verify saat entry pertama
        if vehicle and not vehicle.verified_at:
            vehicle.verification_status      = "verified"
            vehicle.verified_at              = datetime.now(timezone.utc)
            vehicle.verified_gate            = req.gate_id
            # verification_confidence removed from db model, we can skip it
            vehicle.status                   = "active"
            await db.commit()
            logger.info("[%s] Auto-verified on first physical entry via gate %s.", plate, req.gate_id)

        # Broadcast ke dashboard hanya kalau terdaftar
        if vehicle:
            event = {
                "type":          "gate_entry",
                "plate":         plate,
                "plate_raw":     vehicle.plate_raw,
                "gate_id":       req.gate_id,
                "owner":         vehicle.owner,
                "vehicle_model": vehicle.model,
                "confidence":    req.confidence,
                "timestamp":     ts,
            }
            await ws_manager.broadcast_gate_event(event)

        delivered = await mqtt_manager.publish_command(req.gate_id, {
            "action":      "open_gate",
            "duration_ms": 5000,
            "plate":       plate,
        })
        if not delivered:
            logger.error("[%s] Gate '%s' offline or MQTT error — command not delivered!", plate, req.gate_id)

        logger.info("[%s] Entry approved → gate %s opened. Registered=%s",
                    plate, req.gate_id, vehicle is not None)
        return GateTriggerResponse(
            action="open_gate",
            plate_number=plate,
            gate_id=req.gate_id,
            reason="Akses masuk diberikan.",
            session_id=session["entry_time"],
            owner=vehicle.owner if vehicle else None,
            vehicle_model=vehicle.model if vehicle else None,
            timestamp=ts,
        )

    # ── EXIT flow ──────────────────────────────────────────────────────────────────
    else:
        existing = await get_active_session(plate)
        if not existing:
            logger.warning("[%s] No active session — manual verification required.", plate)
            await set_cooldown(plate)
            return GateTriggerResponse(
                action="deny_access",
                plate_number=plate,
                gate_id=req.gate_id,
                reason="Tidak ada sesi aktif. Hubungi admin parkir untuk verifikasi manual.",
                timestamp=ts,
            )

        # Cek apakah tamu belum di-approve
        if existing.get("is_guest") and not existing.get("exit_approved"):
            logger.warning("[%s] Guest session — exit not yet approved by admin.", plate)
            await set_cooldown(plate)
            return GateTriggerResponse(
                action="deny_access",
                plate_number=plate,
                gate_id=req.gate_id,
                reason="Kendaraan tamu belum diizinkan keluar. Hubungi admin parkir.",
                timestamp=ts,
            )

        # Hitung fee
        duration_secs = time.time() - existing.get("entry_ts", time.time())
        duration_hours = max(1, int(duration_secs / 3600) + (1 if duration_secs % 3600 > 0 else 0))
        
        vtype = vehicle.vehicle_type if vehicle else "motor"
        est_fee = (
            min(1000 + (duration_hours - 1) * 1000, 2000)
            if vtype == "motor"
            else min(2000 + (duration_hours - 1) * 1000, 10000)
        )

        payment_method = "manual"
        paid_provider = None

        # Cek saldo e-wallet kalau kendaraan terdaftar
        if vehicle and not existing.get("exit_approved"):
            ewallets = sorted(vehicle.ewallets, key=lambda x: not x.is_primary)
            total_saldo = sum(e.balance for e in ewallets)

            if total_saldo < est_fee:
                logger.warning("[%s] Insufficient balance (Rp%d < Rp%d) — manual payment required.",
                            plate, total_saldo, est_fee)
                # Flag session supaya muncul di admin
                await flag_manual_payment(plate)
                await set_cooldown(plate)
                return GateTriggerResponse(
                    action="deny_access",
                    plate_number=plate,
                    gate_id=req.gate_id,
                    reason=f"Saldo e-wallet tidak cukup (Rp{total_saldo:,} < Rp{est_fee:,}). Hubungi admin untuk pembayaran manual.",
                    timestamp=ts,
                )
            
            # Autodebit from the first ewallet with sufficient balance
            for ew in ewallets:
                if ew.balance >= est_fee:
                    ew.balance -= est_fee
                    payment_method = "autodebit"
                    paid_provider = ew.provider
                    break
            
            if payment_method == "autodebit":
                await db.commit()

        # Build History payload
        history_record = History(
            plate_normalized=plate,
            gate_id=existing.get("gate_id", req.gate_id),
            entry_time=datetime.fromisoformat(existing.get("entry_time")),
            exit_time=datetime.now(timezone.utc),
            duration_secs=int(duration_secs),
            fee=est_fee,
            status="completed",
        )
        
        # Only attach to vehicle if it exists in DB
        if vehicle:
            db.add(history_record)
            await db.commit()
            
        await delete_active_session(plate)
        await set_cooldown(plate)

        if vehicle:
            event = {
                "type":          "gate_exit",
                "plate":         plate,
                "plate_raw":     vehicle.plate_raw,
                "gate_id":       req.gate_id,
                "owner":         vehicle.owner,
                "vehicle_model": vehicle.model,
                "duration_secs": history_record.duration_secs,
                "fee":           est_fee,
                "confidence":    req.confidence,
                "timestamp":     ts,
            }
            await ws_manager.broadcast_gate_event(event)

        await mqtt_manager.publish_command(req.gate_id, {
            "action":      "open_gate",
            "duration_ms": 5000,
            "plate":       plate,
        })

        logger.info("[%s] Exit approved → fee Rp%d → gate %s opened.", plate, est_fee, req.gate_id)
        return GateTriggerResponse(
            action="open_gate",
            plate_number=plate,
            gate_id=req.gate_id,
            reason="Keluar diproses. Billing selesai.",
            fee=est_fee,
            owner=vehicle.owner if vehicle else None,
            vehicle_model=vehicle.model if vehicle else None,
            timestamp=ts,
        )    

async def get_history(db: AsyncSession, limit: int = 50) -> list[dict]:
    """Return the last N parking sessions (newest first)."""
    query = select(History).order_by(desc(History.entry_time)).limit(limit)
    result = await db.execute(query)
    records = result.scalars().all()
    
    return [
        {
            "id": r.id,
            "plate": r.plate_normalized,
            "gate_id": r.gate_id,
            "entry_time": r.entry_time.isoformat() if r.entry_time else None,
            "exit_time": r.exit_time.isoformat() if r.exit_time else None,
            "duration_secs": r.duration_secs,
            "fee": r.fee,
            "status": r.status,
            "gate_location": gate_location(r.gate_id)
        }
        for r in records
    ]
