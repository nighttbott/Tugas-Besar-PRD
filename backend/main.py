"""
main.py — FastAPI application entrypoint.

Run: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi import WebSocket as WS

from core.config import get_settings
from core.database import get_redis, close_redis
from routers.gate import router as gate_router
from routers.vehicles import router as vehicles_router
from routers.admin import router as admin_router
from routers.auth import router as auth_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("🚀 %s v%s starting...", settings.APP_NAME, settings.APP_VERSION)
    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("✅ Redis connection OK.")
    except Exception as e:
        logger.error("❌ Redis connection failed: %s. Running without cache.", e)
    yield
    logger.info("🛑 Shutting down...")
    await close_redis()


settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

#app.add_middleware(
#    TrustedHostMiddleware,
#    allowed_hosts=["localhost", "127.0.0.1", "*.itb.ac.id", "*"],
#)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # ← sementara wildcard
    allow_credentials=False,      # ← HARUS False kalau origins="*"
    allow_methods=["*"],
    allow_headers=["*"],
)

from routers.gate import router as gate_router, ws_router

# ── HTTP Routes ───────────────────────────────────────────────────────────────
app.include_router(gate_router,     prefix="/api/v1/gate",     tags=["Gate"])
app.include_router(vehicles_router, prefix="/api/v1/vehicles", tags=["Vehicles"])
app.include_router(admin_router,    prefix="/api/v1/admin",    tags=["Admin"])
app.include_router(auth_router,     prefix="/api/v1/auth",     tags=["Auth"])

# User auth — prefix terpisah supaya tidak conflict
app.include_router(vehicles_router, prefix="/api/v1/auth", tags=["Auth"])

# ── WebSocket Routes — router terpisah, tidak ada HTTP route di sini ──────────
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"], include_in_schema=False)


@app.post("/api/v1/auth/dev-login", tags=["Auth"])
async def dev_login():
    """Auto-login untuk development. Hanya aktif saat DEBUG=True."""
    if not settings.DEBUG:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found.")
    
    from core.security import create_jwt
    token = create_jwt(
        sub="dashboard_user",
        extra={"nim": "dev", "name": "Developer"},
        ttl_hours=8,
        settings=settings,
    )
    return {"access_token": token, "token_type": "bearer"}


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "service": settings.APP_NAME}

@app.websocket("/ws/test")
async def ws_test(websocket: WS):
    await websocket.accept()
    await websocket.send_text("ok")
    await websocket.close()
