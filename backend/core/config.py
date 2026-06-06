"""
core/config.py
Environment-driven configuration. Create a `.env` file in /backend with these values.
Never commit `.env` to version control.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "ANPR Parking Gate — ITB Jatinangor"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Security ─────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_32_BYTE_HEX"
    JWT_ALGORITHM:  str = "HS256"
    DEBUG:          bool = False

    # ANPR shared secret — set sama di backend .env dan anpr/.env
    ANPR_KEY: str = "local-anpr-secret"

    # ESP32 device keys — format JSON string: {"G1":"key-g1","EXIT1":"key-exit1"}
    # Di .env tulis satu baris: ESP32_DEVICE_KEYS={"G1":"esp32-secret-g1"}
    ESP32_DEVICE_KEYS: str = '{"G1":"esp32-secret-g1"}'

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/anpr_db"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_COOLDOWN_TTL: int = 10       # seconds — duplicate-trigger suppression
    REDIS_SESSION_TTL: int = 86400     # 24 h  — active parking sessions

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Only allow the Next.js dev server and production domain
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "https://six.itb.ac.id"]

    # ── Gate Hardware ─────────────────────────────────────────────────────────
    GATE_OPEN_DURATION_MS: int = 1000  # milliseconds the relay stays HIGH

    # ── MQTT ──────────────────────────────────────────────────────────────────
    MQTT_BROKER_URL: str = "localhost"
    MQTT_BROKER_PORT: int = 1883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
