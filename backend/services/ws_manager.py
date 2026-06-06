"""
services/ws_manager.py
Manages two classes of WebSocket clients:
  1. Dashboard browsers  → /ws/gate-events  (receive-only, read the gate log)
  2. ESP32 gate units    → /ws/esp32/{gate_id} (receive open/close commands)

Thread-safe with asyncio.Lock. Stale connections are silently pruned on send.
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger("ws_manager")


class ConnectionManager:
    def __init__(self):
        # Dashboard subscribers: mapping of WebSocket to user payload dict
        self._dashboard_clients: dict[WebSocket, dict] = {}
        # Gate controllers: one per physical gate
        self._gate_clients: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    # ── Dashboard (browser) ───────────────────────────────────────────────────
    async def connect_dashboard(self, websocket: WebSocket, payload: dict):
        await websocket.accept()
        async with self._lock:
            self._dashboard_clients[websocket] = payload
        logger.info("Dashboard client connected. Total: %d", len(self._dashboard_clients))

    async def disconnect_dashboard(self, websocket: WebSocket):
        async with self._lock:
            self._dashboard_clients.pop(websocket, None)
        logger.info("Dashboard client disconnected. Total: %d", len(self._dashboard_clients))

    async def broadcast_gate_event(self, event: dict, vehicle_nim: str = None):
        """
        Push a gate event JSON to connected dashboard browsers.
        Filter: Admins see everything. Users only see their own vehicles.
        Guests (vehicle_nim=None) are only seen by admins.
        """
        payload = json.dumps(event)
        dead: list[WebSocket] = []

        async with self._lock:
            clients = list(self._dashboard_clients.items())

        for ws, user_payload in clients:
            is_admin = user_payload.get("sub") == "parking_admin"
            user_nim = user_payload.get("nim")
            
            can_see = False
            if is_admin:
                can_see = True
            elif vehicle_nim and vehicle_nim == user_nim:
                can_see = True

            if can_see:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._dashboard_clients.pop(ws, None)

    # ── ESP32 Gate Controllers ────────────────────────────────────────────────
    async def connect_gate(self, gate_id: str, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            # If a stale connection exists for this gate, close it first
            old = self._gate_clients.get(gate_id)
            if old:
                try:
                    await old.close()
                except Exception:
                    pass
            self._gate_clients[gate_id] = websocket
        logger.info("ESP32 gate '%s' connected.", gate_id)

    async def disconnect_gate(self, gate_id: str):
        async with self._lock:
            self._gate_clients.pop(gate_id, None)
        logger.info("ESP32 gate '%s' disconnected.", gate_id)

    async def send_gate_command(self, gate_id: str, command: dict) -> bool:
        """
        Send a JSON command to a specific gate unit.
        Returns True if delivered, False if gate is offline.
        """
        async with self._lock:
            ws: Optional[WebSocket] = self._gate_clients.get(gate_id)

        if not ws:
            logger.warning("Gate '%s' is offline — command not delivered.", gate_id)
            return False

        try:
            await ws.send_text(json.dumps(command))
            return True
        except Exception as e:
            logger.error("Failed to send command to gate '%s': %s", gate_id, e)
            await self.disconnect_gate(gate_id)
            return False

    def gate_is_online(self, gate_id: str) -> bool:
        return gate_id in self._gate_clients

    @property
    def dashboard_count(self) -> int:
        return len(self._dashboard_clients)

    @property
    def online_gates(self) -> list[str]:
        return list(self._gate_clients.keys())


# ── Module-level singleton shared across all routers ─────────────────────────
ws_manager = ConnectionManager()
