from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings

# Get settings (Assume DATABASE_URL is added to config or use a default)
settings = get_settings()
DATABASE_URL = getattr(settings, "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/anpr_db")

# 1. Buat AsyncEngine
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set True untuk melihat query SQL di console
    pool_size=10,
    max_overflow=20,
)

# 2. Buat factory session asinkron
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# 3. Dependency function untuk digunakan di router FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection database session.
    Akan membuat session saat request masuk, dan menutupnya setelah request selesai.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
