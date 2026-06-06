"""
routers/gate.py
HTTP and WebSocket routes for the gate system.

Routes:
  POST /api/v1/gate/trigger          ← ANPR script (Bearer token required)
  GET  /api/v1/gate/history          ← Dashboard fetch (Bearer token required)
  GET  /api/v1/gate/status           ← Health / gate online status (public)
  WS   /ws/gate-events               ← Dashboard live feed (token query param)
  WS   /ws/esp32/{gate_id}           ← ESP32 gate controller (token query param)
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from core.config import get_settings, Settings
from core.security import require_anpr_key, require_dashboard_token, verify_esp32_device_key
from models.gate import GateTriggerRequest, GateTriggerResponse
from services.gate_service import process_gate_trigger, get_history
from services.ws_manager import ws_manager

from sqlalchemy.ext.asyncio import AsyncSession
from core.database_sql import get_db

logger = logging.getLogger("gate_router")

router = APIRouter()


# ── POST /api/v1/gate/trigger ─────────────────────────────────────────────────
@router.post(
    "/trigger",
    response_model=GateTriggerResponse,
    summary="ANPR Gate Trigger",
    description=(
        "Receives a validated plate number from the ANPR edge script. "
        "Performs security checks, database lookup, and instructs the "
        "physical gate via WebSocket. Requires ANPR service Bearer token."
    ),
)
async def gate_trigger(
    request: GateTriggerRequest,
    _: Annotated[None, Depends(require_anpr_key)],
    db: AsyncSession = Depends(get_db)
) -> GateTriggerResponse:
    return await process_gate_trigger(request, db)


# ── GET /api/v1/gate/history ──────────────────────────────────────────────────
@router.get(
    "/history",
    summary="Parking session history",
)
async def parking_history(
    _token_payload: Annotated[dict, Depends(require_dashboard_token)],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, le=200),
) -> list[dict]:
    return await get_history(db, limit=limit)


# ── GET /api/v1/gate/status ───────────────────────────────────────────────────
@router.get("/status", summary="System health & gate connectivity")
async def gate_status():
    from core.mqtt_manager import mqtt_manager
    
    # Kumpulkan hanya gate yang value-nya True (online)
    online_gates = [gate_id for gate_id, is_online in mqtt_manager.online_gates.items() if is_online]
    
    return {
        "api": "ok",
        "dashboard_clients": ws_manager.dashboard_count,
        "online_gates": online_gates,
    }


# ── WS /ws/gate-events (Dashboard) ───────────────────────────────────────────
@router.websocket("/gate-events")
async def dashboard_ws(
    websocket: WebSocket,
    token: str = Query(..., description="Dashboard JWT token"),
    settings: Settings = Depends(get_settings),
):
    """
    Dashboard browsers connect here to receive real-time gate events.
    Token is validated before accepting the connection.
    Note: For Next.js, use the custom hook `useGateEvents` which handles
    reconnection and token injection automatically.
    """
    from jose import jwt, JWTError

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("sub") not in ("dashboard_user", "parking_admin"):
            raise JWTError("bad sub")
    except JWTError:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await ws_manager.connect_dashboard(websocket)
    try:
        while True:
            # Keep connection alive; browser sends pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect_dashboard(websocket)


# ── WS /ws/esp32/{gate_id} (Hardware) ────────────────────────────────────────
@router.websocket("/esp32/{gate_id}")
async def esp32_ws(
    websocket: WebSocket,
    gate_id: str,
    device_key: str = Query(..., description="ESP32 device key"),
    settings: Settings = Depends(get_settings),
):
    
    """
    Each ESP32 gate unit connects here on boot and holds the connection open.
    The backend pushes {"action":"open_gate","duration_ms":1000} on plate match.
    """
    print(f"[DEBUG] ESP32 WS hit — gate_id={repr(gate_id)} device_key={repr(device_key)}")
    if not verify_esp32_device_key(device_key, settings):
        await websocket.close(code=4001, reason="Unauthorized")
        logger.warning("ESP32 gate '%s' rejected — bad token.", gate_id)
        return

    await ws_manager.connect_gate(gate_id, websocket)
    logger.info("Gate '%s' online.", gate_id)

    try:
        while True:
            # ESP32 sends heartbeat pings ("ping"); backend ignores content
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.warning("Gate '%s' disconnected.", gate_id)
        await ws_manager.disconnect_gate(gate_id)

ws_router = APIRouter()

@ws_router.websocket("/gate-events")
async def dashboard_ws_2(
    websocket: WebSocket,
    token: str = Query(...),
    settings: Settings = Depends(get_settings),
):
    from jose import jwt, JWTError
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("sub") not in ("dashboard_user", "parking_admin"):
            raise JWTError("bad sub")
    except JWTError:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await ws_manager.connect_dashboard(websocket, payload)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect_dashboard(websocket)


@ws_router.websocket("/esp32/{gate_id}")
async def esp32_ws_2(
    websocket: WebSocket,
    gate_id: str,
    device_key: str = Query(...),
    settings: Settings = Depends(get_settings),
):
    print(f"[DEBUG] ESP32 WS hit — gate_id={repr(gate_id)} device_key={repr(device_key)}")
    if not verify_esp32_device_key(device_key, settings):
        await websocket.close(code=4001, reason="Unauthorized")
        logger.warning("ESP32 gate '%s' rejected — bad device_key.", gate_id)
        return
    await ws_manager.connect_gate(gate_id, websocket)
    logger.info("Gate '%s' online.", gate_id)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.warning("Gate '%s' disconnected.", gate_id)
        await ws_manager.disconnect_gate(gate_id)
