"""
FastAPI 应用入口
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import time
import uuid
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.v1.api import api_router
from app.core.database import get_db
from app.tools.registry import get_tool_registry
from app.tools.init import init_tools
from app.core.rate_limit import RateLimiter
from app.core.default_prompts import ensure_default_prompts
from app.ai.gateway import ModelProviderUnavailableError

# 设置日志
setup_logging(settings.LOG_LEVEL)
rate_limiter = RateLimiter(settings.RATE_LIMIT_PER_MINUTE, settings.RATE_LIMIT_PER_HOUR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    print("Initializing tools...")
    async for db in get_db():
        registry = get_tool_registry()
        init_tools(db, registry)
        prompt_count = await ensure_default_prompts(db)
        print(f"Initialized {prompt_count} missing default prompts")
        print(f"Registered {len(registry.list_all_tools())} tools")
        break

    yield

    # 关闭时清理
    print("Shutting down...")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    description="学生智能问答系统 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 请求 ID 中间件
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """为每个请求添加唯一 ID"""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    # Keep health probes available while applying configured limits to API
    # traffic. Authorization and tenant checks remain in the route handlers.
    if not request.url.path.startswith(("/api/v1/health", "/api/health")):
        # The public gateway overwrites X-Real-IP with the actual client
        # address. Using only request.client.host would put every browser
        # behind nginx into the same rate-limit bucket.
        client_host = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
        allowed, retry_after = rate_limiter.allow(client_host)
        if not allowed:
            return JSONResponse(
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "X-Error-Code": "RATE_LIMIT_EXCEEDED",
                    "X-Request-ID": request_id,
                },
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "请求过于频繁，请稍后重试",
                        "request_id": request_id,
                        "details": {"retry_after": retry_after},
                    }
                },
            )

    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = str(process_time)
    response.headers.setdefault("X-RateLimit-Limit", str(settings.RATE_LIMIT_PER_MINUTE))

    return response


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    request_id = getattr(request.state, "request_id", "unknown")

    if isinstance(exc, ModelProviderUnavailableError):
        return JSONResponse(
            status_code=503,
            headers={"X-Error-Code": "MODEL_PROVIDER_NOT_CONFIGURED"},
            content={
                "error": {
                    "code": "MODEL_PROVIDER_NOT_CONFIGURED",
                    "message": str(exc),
                    "request_id": request_id,
                    "details": {"configure": ["OPENAI_API_KEY", "DEEPSEEK_API_KEY"]},
                },
            },
        )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "服务器内部错误",
                "request_id": request_id,
                "details": {},
            },
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", "unknown")
    code = exc.headers.get("X-Error-Code") if exc.headers else None
    code = code or f"HTTP_{exc.status_code}"
    details = getattr(exc, "details", None)
    if details is None:
        details = exc.detail if isinstance(exc.detail, dict) else {}
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "error": {
                "code": code,
                "message": exc.detail if isinstance(exc.detail, str) else "请求失败",
                "request_id": request_id,
                "details": details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求参数不合法",
                "request_id": request_id,
                "details": {"fields": exc.errors()},
            }
        },
    )


# 注册路由
app.include_router(api_router, prefix="/api/v1")


# 根路径
@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
    }


# 健康检查
@app.get("/api/health")
async def health_check():
    """Backward-compatible alias for ``/api/v1/health``."""
    from datetime import datetime, timezone

    return {
        "status": "ok",
        "service": "api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.APP_ENV,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
