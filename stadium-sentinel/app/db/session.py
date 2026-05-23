from typing import AsyncIterator
from sqlalchemy.ext.asyncio import (
    create_async_engine, async_sessionmaker, AsyncSession,
)
from app.config import settings

engine = create_async_engine(
    settings.POSTGRES_DSN,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,        # detect dead connections before issuing query
    pool_recycle=1800,         # recycle every 30 min — Cloud SQL kills idle > 1h
    echo=False,                # flip to True only when debugging SQL
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,    # let us read attrs after commit without re-fetch
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Guarantees session.close() even on exception."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def dispose_engine() -> None:
    """Call on app shutdown."""
    await engine.dispose()
