"""
FastAPI 应用入口
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException
import time
import uuid
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.logging import bind_context, clear_context, get_logger, setup_logging
from app.api.v1.api import api_router
from app.core.database import get_db
from app.tools.registry import get_tool_registry
from app.tools.init import init_tools
from app.core.rate_limit import RateLimiter
from app.core.default_prompts import ensure_default_prompts
from app.ai.gateway import ModelProviderUnavailableError

# 设置日志
setup_logging(settings.LOG_LEVEL, settings.LOG_FILE)
logger = get_logger(__name__)
rate_limiter = RateLimiter(settings.RATE_LIMIT_PER_MINUTE, settings.RATE_LIMIT_PER_HOUR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("initializing_tools")
    async for db in get_db():
        registry = get_tool_registry()
        init_tools(db, registry)
        prompt_count = await ensure_default_prompts(db)
        logger.info("tools_initialized", default_prompts_created=prompt_count, tool_count=len(registry.list_all_tools()))
        break

    yield

    # 关闭时清理
    logger.info("shutting_down")


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
    """为每个请求添加唯一 ID，并绑定到结构化日志上下文。"""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    clear_context()
    bind_context(request_id=request_id, path=request.url.path, method=request.method)
    start_time = time.perf_counter()
    try:
        response = None
        # Keep health probes available while limiting other requests. The
        # gateway supplies X-Real-IP so browsers have separate buckets.
        if not request.url.path.startswith(("/api/v1/health", "/api/health")):
            client_host = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
            allowed, retry_after = rate_limiter.allow(client_host)
            if not allowed:
                response = JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after), "X-Error-Code": "RATE_LIMIT_EXCEEDED"},
                    content={
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": "请求过于频繁，请稍后重试",
                            "request_id": request_id,
                            "details": {"retry_after": retry_after},
                        }
                    },
                )
        if response is None:
            try:
                response = await call_next(request)
            except Exception as exc:
                # Handle failures before returning from the request context,
                # so error logs and response headers share the same ID.
                response = await global_exception_handler(request, exc)
        process_time = time.perf_counter() - start_time
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(process_time)
        response.headers.setdefault("X-RateLimit-Limit", str(settings.RATE_LIMIT_PER_MINUTE))
        log = logger.error if response.status_code >= 500 else logger.warning if response.status_code >= 400 else logger.info
        log("request_completed", status_code=response.status_code, duration_ms=round(process_time * 1000, 2))
        return response
    finally:
        clear_context()


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    request_id = getattr(request.state, "request_id", "unknown")

    if isinstance(exc, ModelProviderUnavailableError):
        logger.error("model_provider_unavailable", request_id=request_id, error_type=type(exc).__name__)
        return JSONResponse(
            status_code=503,
            headers={"X-Error-Code": "MODEL_PROVIDER_NOT_CONFIGURED", "X-Request-ID": request_id},
            content={
                "error": {
                    "code": "MODEL_PROVIDER_NOT_CONFIGURED",
                    "message": str(exc),
                    "request_id": request_id,
                    "details": {"configure": ["OPENAI_API_KEY", "DEEPSEEK_API_KEY"]},
                },
            },
        )
    logger.error(
        "unhandled_exception",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        error_type=type(exc).__name__,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        headers={"X-Error-Code": "INTERNAL_SERVER_ERROR", "X-Request-ID": request_id},
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "服务器内部错误",
                "request_id": request_id,
                "details": {},
            },
        },
    )


# 注意：这里必须注册 Starlette 的 HTTPException，它是 FastAPI HTTPException
# 的父类。若只注册 FastAPI 版本，框架自身产生的 404/405 会绕过统一格式。
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    request_id = getattr(request.state, "request_id", "unknown")
    code = exc.headers.get("X-Error-Code") if exc.headers else None
    # 只为框架自身产生的 404/405 补上稳定错误码，保留业务路由抛出的
    # 具体提示（例如“用户名或密码错误”），不要把 401/403 一并泛化。
    framework_defaults = {404: "Not Found", 405: "Method Not Allowed"}
    if code is None and exc.detail == framework_defaults.get(exc.status_code):
        code = {
            404: "RESOURCE_NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
        }[exc.status_code]
    code = code or f"HTTP_{exc.status_code}"

    # 支持新的统一错误格式
    if isinstance(exc.detail, dict):
        message = exc.detail.get("message", "请求失败")
        user_message = exc.detail.get("user_message", message)
        details = exc.detail.get("details", {})
    else:
        message = exc.detail if isinstance(exc.detail, str) else "请求失败"
        user_message = message
        details = getattr(exc, "details", {})

    # 友好的错误消息映射
    friendly_messages = {
        "RATE_LIMIT_EXCEEDED": "请求过于频繁，请稍后再试",
        "SESSION_NOT_FOUND": "会话不存在或已过期",
        "MESSAGE_NOT_FOUND": "消息不存在",
        "RESOURCE_NOT_FOUND": "请求的资源不存在",
        "VALIDATION_ERROR": "请求参数不正确",
        "ENTITLEMENT_REQUIRED": "当前没有有效的诊断报告授权，请联系学校确认。",
        "ADMIN_REQUIRED": "需要管理员权限",
        "UNAUTHORIZED": "请先登录",
        "FORBIDDEN": "没有访问该资源的权限",
        "METHOD_NOT_ALLOWED": "请求方法不被支持",
    }

    user_message = friendly_messages.get(code, user_message)

    return JSONResponse(
        status_code=exc.status_code,
        headers={**(exc.headers or {}), "X-Error-Code": code, "X-Request-ID": request_id},
        content={
            "error": {
                "code": code,
                "message": user_message,  # 用户友好的消息
                "technical_message": message,  # 技术详情（可选）
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
        headers={"X-Error-Code": "VALIDATION_ERROR", "X-Request-ID": request_id},
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求参数不合法",
                "request_id": request_id,
                "details": {"fields": [{"loc": list(error["loc"]), "type": error["type"], "msg": error["msg"]} for error in exc.errors()]},  # Never echo uploaded content or credentials.
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
