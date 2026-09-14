"""
健康检查端点
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime
try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover - dependency is present in production images
    redis = None

from app.core.database import get_db
from app.core.config import settings
from app.ai.gateway import get_model_gateway

router = APIRouter()


@router.get("")
async def health_check():
    """基础健康检查"""
    model_status = get_model_gateway().runtime_status
    return {
        "status": "ok" if model_status["real_model_ready"] else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.APP_ENV,
        "model": model_status,
    }


@router.get("/db")
async def health_check_db(db: AsyncSession = Depends(get_db)):
    """数据库健康检查"""
    try:
        await db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "service": "postgresql",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库暂时不可用",
            headers={"X-Error-Code": "DATABASE_UNAVAILABLE"},
        ) from e


@router.get("/redis")
async def health_check_redis():
    """Redis 健康检查"""
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="缓存服务暂时不可用",
            headers={"X-Error-Code": "REDIS_UNAVAILABLE"},
        )
    try:
        r = redis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.close()
        return {
            "status": "ok",
            "service": "redis",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="缓存服务暂时不可用",
            headers={"X-Error-Code": "REDIS_UNAVAILABLE"},
        ) from e
