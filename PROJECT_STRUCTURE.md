# ANPR Parking Gate System — ITB Jatinangor
## Project Structure (WSL2 + VS Code Monorepo)

```
anpr-parking/
│
├── .gitignore                               # Ignores .env, node_modules, *.pt, build artifacts
├── PROJECT_STRUCTURE.md                     # This file
│
├── backend/                                 # FastAPI (Python 3.11+)
│   ├── __init__.py
│   ├── main.py                              # App entrypoint: CORS, lifespan, 3 router registrations
│   ├── requirements.txt                     # fastapi, uvicorn, python-jose, redis, pydantic-settings
│   ├── .env.example                         # Secret template → copy to .env
│   ├── db.json                              # ← PERSISTENT STORAGE (auto-created on first run)
│   │                                        #   Survives server restarts. Contains VEHICLE_DB.
│   │                                        #   Written by save_vehicle_db() after every mutation.
│   │                                        #   Add to .gitignore in production.
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                        # Pydantic-settings: JWT keys, Redis URL, CORS, tokens
│   │   ├── security.py                      # JWT encode/decode + 4 role-based dependencies:
│   │   │                                    #   require_anpr_token      → sub: anpr_service
│   │   │                                    #   require_dashboard_token → sub: dashboard_user
│   │   │                                    #   require_admin_token     → sub: parking_admin
│   │   │                                    #   verify_esp32_token      → sub: esp32_gate
│   │   │                                    # Token generators:
│   │   │                                    #   create_anpr_service_token()
│   │   │                                    #   create_esp32_gate_token()
│   │   │                                    #   create_dashboard_token()
│   │   │                                    #   create_admin_token()
│   │   └── database.py                      # Two-tier storage:
│   │                                        #   VEHICLE_DB dict  → backed by db.json (persistent)
│   │                                        #   HISTORY_DB list  → in-memory (resets on restart)
│   │                                        #   SUPPORTED_EWALLETS: GoPay, OVO, ShopeePay, Dana, LinkAja
│   │                                        #   save_vehicle_db() → writes VEHICLE_DB to db.json
│   │                                        #   Redis: session CRUD, cooldown, balance deduction on exit
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── gate.py                          # Pydantic: GateTriggerRequest, GateTriggerResponse
│   │   └── vehicle.py                       # Pydantic: RegisteredVehicle, EWallet, ActiveSession
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── gate.py                          # Gate trigger + WebSocket routes:
│   │   │                                    #   POST /api/v1/gate/trigger  (anpr_service token)
│   │   │                                    #   GET  /api/v1/gate/history  (dashboard_user token) ← FIXED
│   │   │                                    #   GET  /api/v1/gate/status   (public)
│   │   │                                    #   WS   /ws/gate-events       (dashboard WS)
│   │   │                                    #   WS   /ws/esp32/{gate_id}   (ESP32 WS)
│   │   │
│   │   ├── vehicles.py                      # Student vehicle CRUD + e-wallet management:
│   │   │                                    #   GET    /api/v1/vehicles/                     (list)
│   │   │                                    #   POST   /api/v1/vehicles/                     (add)
│   │   │                                    #   DELETE /api/v1/vehicles/{plate}              (remove)
│   │   │                                    #   GET    /api/v1/vehicles/sessions             (stats)
│   │   │                                    #   POST   /api/v1/vehicles/{plate}/ewallet      (add)
│   │   │                                    #   PUT    /api/v1/vehicles/{plate}/ewallet/{p}/balance
│   │   │                                    #   DELETE /api/v1/vehicles/{plate}/ewallet/{p} (remove)
│   │   │                                    #   PUT    /api/v1/vehicles/{plate}/ewallet/{p}/primary
│   │   │                                    #   PUT    /api/v1/vehicles/{plate}/verify       (ANPR verify)
│   │   │                                    #   All require: dashboard_user token
│   │   │                                    #   All mutations call save_vehicle_db() immediately
│   │   │
│   │   └── admin.py                         # Admin-only routes (parking_admin token):
│   │                                        #   POST /api/v1/admin/auth/token           (login → JWT)
│   │                                        #   GET  /api/v1/admin/vehicles             (all vehicles)
│   │                                        #   POST /api/v1/admin/vehicles/{p}/verify-anpr
│   │                                        #   POST /api/v1/admin/vehicles/{p}/unverify-anpr
│   │                                        #   Both verify/unverify call save_vehicle_db()
│   │
│   └── services/
│       ├── __init__.py
│       ├── gate_service.py                  # Gate decision tree (5 steps):
│       │                                    #   1. confidence ≥ 0.85 (OCR vote consistency)
│       │                                    #   2. Redis cooldown check
│       │                                    #   3. Plate exists in VEHICLE_DB
│       │                                    #   4. anpr_verified == True  ← AUTHORITATIVE check
│       │                                    #   5. status != "blocked"
│       │                                    #   Entry: create Redis session
│       │                                    #   Exit:  deduct e-wallet balance, archive to HISTORY_DB
│       └── ws_manager.py                    # WebSocket connection manager:
│                                            #   dashboard fan-out broadcast
│                                            #   ESP32 per-gate command delivery
│                                            #   GateStatusChips polls /gate/status every 5s
│
├── frontend/                                # Next.js 14 (App Router, TypeScript)
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.ts                       # images: unoptimized, API proxy rewrites, cache headers
│   ├── .env.local.example                   # Template → copy to .env.local
│   │
│   ├── app/
│   │   ├── globals.css                      # Single CSS source of truth:
│   │   │                                    #   .site-container — shared alignment class used by
│   │   │                                    #     Navbar inner div, Breadcrumb wrapper, .page div
│   │   │                                    #     (padding: 20px, max-width: 1200px, margin: auto)
│   │   │                                    #   @import Bootstrap 3.3.7, Roboto, Font Awesome 5
│   │   │                                    #   Verbatim style-20200730.css rules (real SIX)
│   │   │                                    #   All parking component styles
│   │   │                                    #   Responsive: ≤992px, ≤768px, ≤480px
│   │   │
│   │   ├── layout.tsx                       # Root layout: import globals.css, metadata
│   │   ├── page.tsx                         # Root → redirect to /parkir
│   │   │
│   │   ├── parkir/
│   │   │   └── page.tsx                     # Student parking dashboard:
│   │   │                                    #   Fetches vehicles from backend on mount
│   │   │                                    #   Add vehicle with live Indonesian plate validation
│   │   │                                    #   Delete vehicle (blocked if currently parked)
│   │   │                                    #   Passes token down to all child components
│   │   │
│   │   ├── admin/
│   │   │   └── page.tsx                     # Admin panel (URL: /admin):
│   │   │                                    #   Login screen → POST /api/v1/admin/auth/token
│   │   │                                    #   Session in sessionStorage (clears on tab close)
│   │   │                                    #   Vehicle table: all vehicles, search, filter by ANPR
│   │   │                                    #   Per-row: verify ANPR with notes / revoke
│   │   │                                    #   Stat cards: total / verified / unverified / parked
│   │   │
│   │   └── api/auth/token/route.ts          # Next.js API route: issue dashboard JWT
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Navbar.tsx                   # Pixel-accurate SIX navbar (from struktur.html source):
│   │   │   │                                #   Uses .site-container for alignment
│   │   │   │                                #   background #222, fa-home (font-size 18)
│   │   │   │                                #   #9d9d9d text, #080808 on hover/active
│   │   │   │                                #   fa-user-circle-o + Bootstrap caret
│   │   │   └── Breadcrumb.tsx               # Bootstrap ol.breadcrumb:
│   │   │                                    #   Uses .site-container wrapper (margin-top: 18px gap)
│   │   │                                    #   border-radius 4px → "separate rectangle" look
│   │   │                                    #   separator »
│   │   │
│   │   ├── parking/
│   │   │   ├── TabMenu.tsx                  # 4-tab switcher
│   │   │   ├── VehicleCard.tsx              # Vehicle row + full e-wallet panel:
│   │   │   │                                #   Real PNG logos from /img/ewallet/
│   │   │   │                                #   useMemo for addProvider (fixes stale state bug)
│   │   │   │                                #   Badge: "Aktif" only if anpr_verified=true AND active
│   │   │   │                                #   onUpdated: optional, guarded with typeof check
│   │   │   ├── ParkingStatus.tsx            # Status tab:
│   │   │   │                                #   session.primary_ewallet (fixed field name)
│   │   │   │                                #   GateStatusChips polls every 5s
│   │   │   ├── HistoryTable.tsx             # Riwayat tab: GET /api/v1/gate/history (dashboard token)
│   │   │   └── TarifInfo.tsx                # Tarif tab: calculator + rate cards
│   │   │
│   │   └── ui/
│   │       ├── Badge.tsx
│   │       ├── PlateTag.tsx
│   │       └── LiveGateEvent.tsx            # Real-time gate feed:
│   │                                        #   Shows "Menunggu aktivitas gerbang..." when empty
│   │                                        #   null token → shows setup message
│   │
│   ├── hooks/
│   │   ├── useGateEvents.ts                 # WS hook: exponential backoff, onEvent callback
│   │   └── useParkingHistory.ts             # SWR hook: polls history every 60s
│   │
│   ├── lib/
│   │   └── api.ts                           # Typed fetch wrapper:
│   │                                        #   ActiveSession.primary_ewallet (fixed field name)
│   │                                        #   validatePlate() — Indonesian regex
│   │                                        #   vehicleApi / gateApi / buildGateEventsWsUrl
│   │
│   └── public/
│       ├── css/                             # SIX portal static CSS (no build step)
│       │   ├── bootstrap.min.css
│       │   ├── bootstrap-theme.min.css
│       │   ├── roboto.css
│       │   ├── all.css                      # paths fixed: /webfonts/
│       │   ├── v4-shims.css
│       │   ├── bootstrap-notifications.min.css
│       │   └── jquery-confirm.min.css
│       ├── img/
│       │   └── ewallet/                     # Real e-wallet logos (PNG, served at /img/ewallet/)
│       │       ├── gopay.png
│       │       ├── ovo.png
│       │       ├── shopeepay.png
│       │       ├── dana.png
│       │       └── linkaja.png
│       └── webfonts/                        # Font Awesome webfonts (fa-solid-900.woff2 etc.)
│                                            # Download from FA 5.15.4 or use CDN fallback
│
├── anpr/                                    # ANPR Edge Script (Windows PowerShell / Python)
│   ├── anpr_main.py                         # YOLOv8 + fast_plate_ocr, async HTTP via aiohttp
│   │                                        #   load_dotenv() → reads .env automatically
│   │                                        #   OCR-based confidence (vote consistency, NOT YOLO score)
│   │                                        #   compute_ocr_confidence() → passes 0.0–1.0 to backend
│   │                                        #   YOLO_MIN_CONF=0.25 (separate from backend threshold)
│   │                                        #   Non-blocking: asyncio.run_coroutine_threadsafe()
│   ├── requirements.txt                     # ultralytics, fast-plate-ocr, opencv-python, aiohttp,
│   │                                        # python-dotenv  ← required for .env auto-loading
│   └── .env                                 # API_ENDPOINT, API_SECRET_KEY (= ANPR_SERVICE_TOKEN),
│                                            # CAMERA_INDEX, GATE_ID, GATE_DIRECTION
│                                            # NO inline comments on value lines (breaks dotenv)
│
├── firmware/
│   └── esp32_gate/
│       ├── esp32_gate.ino                   # ESP32 WebSocket gate controller
│       └── README.md                        # Wiring, libraries, flashing guide
│
└── docs/
    ├── SECURITY.md                          # Threat model, tokens, TLS, data persistence
    └── DEPLOYMENT.md                        # Full setup guide (WSL2 backend + Windows ANPR)
```

---

## Role & Token Architecture

```
┌──────────────────┬──────────────────┬───────────┬────────────────────────────────────┐
│ Client           │ sub claim        │ TTL       │ Protected endpoints                 │
├──────────────────┼──────────────────┼───────────┼────────────────────────────────────┤
│ ANPR script      │ anpr_service     │ 365 days  │ POST /gate/trigger only             │
│ Dashboard user   │ dashboard_user   │ 8 hours   │ /vehicles/* + GET /gate/history     │
│ Admin (petugas)  │ parking_admin    │ 365 days  │ /admin/* only                       │
│ ESP32 gate unit  │ esp32_gate       │ 30 days   │ WS /ws/esp32/{gate_id}              │
└──────────────────┴──────────────────┴───────────┴────────────────────────────────────┘
```

**Admin credentials** (in `routers/admin.py` → `ADMIN_USERS`):

| Username | Password |
|---|---|
| `admin` | `parkir2024` |
| `petugas` | `gerbang123` |

---

## ANPR Gate Decision Tree

```
POST /api/v1/gate/trigger
  ├─ 1. OCR confidence ≥ 0.85?          NO → low_confidence (gate holds)
  ├─ 2. Redis cooldown active?           YES → cooldown (duplicate ignored)
  ├─ 3. Plate in VEHICLE_DB?            NO → deny_access (unregistered)
  ├─ 4. anpr_verified == True?          NO → deny_access (not verified by petugas)
  ├─ 5. status == "blocked"?            YES → deny_access (explicitly banned)
  └─ PASS → open_gate
       ├─ Entry: create Redis session, broadcast WS event, send ESP32 command
       └─ Exit:  deduct e-wallet balance, archive to HISTORY_DB, open gate
```

**Important:** Step 4 checks `anpr_verified`, NOT `status`. A vehicle with
`anpr_verified=True` opens the gate regardless of `status` field (unless blocked).

---

## E-Wallet & Balance Flow

```
Add e-wallet via web (GoPay/OVO/ShopeePay/Dana/LinkAja)
  → Set initial balance (customizable anytime via "Edit Saldo")
  → Balance persisted in db.json via save_vehicle_db()

Gate exit trigger:
  close_session() in database.py:
    → Try Primary e-wallet: balance -= fee
    → If balance < fee: try Cadangan
    → If both fail: payment_method = "manual"
    → save_vehicle_db() called → balance change persists to db.json
```

---

## Confidence Architecture (ANPR)

```
YOLO score (0.3–0.7)      → "Is there a plate in this box?"
                              Only used to filter noise (YOLO_MIN_CONF=0.25)

OCR vote consistency      → "How sure are we of the plate text?"
(0.0–1.0)                   = best_plate_count / len(history)
                              Sent to backend as `confidence`
                              Backend threshold: ≥ 0.85

Example: 9/10 OCR readings agree → ocr_confidence = 0.90 → gate opens
```

---

## Data Persistence

```
db.json (backend/) — written on every mutation, read on startup
  ├── Vehicles added via web (/parkir) ✓
  ├── E-wallets added/removed ✓
  ├── Balance changes (autodebit + manual edit) ✓
  ├── ANPR verifications (admin panel) ✓
  └── ANPR revocations ✓

NOT persisted (resets on server restart):
  ├── HISTORY_DB (completed sessions) — use PostgreSQL for production
  └── Redis sessions (active parking) — Redis is persistent if configured
```

---

## CSS Alignment System

```
.site-container {                    ← single shared class
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
}

Used by:
  Navbar inner div   → className="site-container"  (nav items align left edge)
  Breadcrumb wrapper → className="site-container"  (breadcrumb aligns left edge)
  Page content       → className="page site-container" (content aligns left edge)

All three share one CSS rule → pixel-identical left edges on any screen width.
```

---

## Quick Start

### Backend (WSL2)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill JWT_SECRET_KEY, generate tokens
sudo service redis-server start
uvicorn main:app --reload --port 8000
# db.json created automatically on first vehicle add
```

### Frontend (WSL2)
```bash
cd frontend
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_DASHBOARD_TOKEN
npm run dev
# Student: http://localhost:3000/parkir
# Admin:   http://localhost:3000/admin
```

### ANPR Script (Windows PowerShell)
```powershell
cd anpr
# Activate venv
.\.venv\Scripts\Activate.ps1

# Install dependencies (includes python-dotenv)
pip install -r requirements.txt

# Create .env with NO inline comments
# API_SECRET_KEY = same value as ANPR_SERVICE_TOKEN in backend/.env
# Then just run:
python anpr_main.py
```

### Admin Panel
```
1. http://localhost:3000/admin
2. Login: admin / parkir2024
3. Find vehicle → "Verifikasi ANPR" → gate now opens for that plate
```

### TOKEN
1. JWT_SECRET_KEY : python -c "import secrets; print(secrets.token_hex(32))"
Location : backend/.env
2. ANPR_SERVICE_TOKEN : python -c "
from core.config import get_settings
from core.security import create_anpr_service_token
print(create_anpr_service_token(get_settings()))
"
Location : backend/.env, anpr/.env
3. ESP32_GATE_TOKEN : 
G1 : python -c "
from core.config import get_settings
from core.security import create_esp32_gate_token
print(create_esp32_gate_token('G1', get_settings()))
"
EXIT : python -c "
from core.config import get_settings
from core.security import create_esp32_gate_token
print(create_esp32_gate_token('EXIT1', get_settings()))
"
Location : backend/.env, firmware/esp32_gate/esp32_gate.ino
Contoh : static const char* WS_URL =
"ws://192.168.1.100:8000/ws/esp32/G1?token=eyJhbGci...";
4. NEXT_PUBLIC_DASHBOARD_TOKEN : python -c "
from core.config import get_settings
from core.security import create_dashboard_token
print(create_dashboard_token('2021184750', get_settings()))
"
Location : frontend/.env.local