"""
结构化日志配置 - 使用 structlog 并接入标准 logging 处理器

关键点：structlog 的日志事件必须经过标准 ``logging`` 的 Handler 输出，
这样文件 Handler、第三方库日志、日志级别过滤和异常堆栈渲染才能统一生效。
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog


def _resolve_log_path(log_file: str | None) -> Path | None:
    """返回可写的日志文件路径；不可写时返回 ``None``。"""
    requested_file = log_file or os.getenv("LOG_FILE", "/app/logs/app.log")
    log_path = Path(requested_file)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return log_path
    except OSError:
        # /app 是容器内路径。本地开发和测试可能没有权限创建，
        # 退回到工作区的 logs 目录，避免应用导入直接失败。
        fallback = Path("logs") / "app.log"
        try:
            fallback.parent.mkdir(parents=True, exist_ok=True)
            return fallback
        except OSError:
            return None


def setup_logging(log_level: str = "INFO", log_file: str | None = None) -> None:
    """配置结构化日志系统。"""
    log_path = _resolve_log_path(log_file)
    level = getattr(logging, str(log_level).upper(), logging.INFO)

    # 这些处理器同时用于 structlog 事件和标准 logging 记录（foreign）。
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.ExtraAdder(),
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    # 让 structlog 事件最终交给标准 logging 的 Handler。
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        # Consult logging's current level even for already-bound loggers.
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            # 把 exc_info 渲染成真正的堆栈，而不是只留下 exc_info=True。
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        if getattr(handler, "_student_agent_handler", False):
            handler.close()
    root_logger.setLevel(level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler._student_agent_handler = True
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if log_path is not None:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler._student_agent_handler = True
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # 设置第三方库日志级别
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.propagate = True
        server_logger.setLevel(level)
    for name in ("sqlalchemy", "asyncio", "httpx", "openai"):
        logging.getLogger(name).setLevel(max(level, logging.WARNING))

    get_logger(__name__).info(
        "structured_logging_initialized",
        level=log_level,
        log_file=str(log_path) if log_path else None,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """获取指定名称的 structlog logger。"""
    return structlog.get_logger(name)


def bind_context(**kwargs) -> None:
    """补充当前请求的日志字段。"""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """在请求开始和结束时清理上下文，避免字段泄漏到后续请求。"""
    structlog.contextvars.clear_contextvars()
