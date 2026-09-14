"""
日志配置
"""
import logging
import sys
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from pythonjsonlogger import jsonlogger


def setup_logging(log_level: str = "INFO", log_file: str | None = None):
    """配置日志系统"""

    # 创建日志目录
    requested_file = log_file or os.getenv("LOG_FILE", "/app/logs/app.log")
    log_path = Path(requested_file)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        # /app is the container path.  Local development and tests may not
        # have permission to create it, so fall back to a workspace-relative
        # log directory instead of failing application import.
        log_path = Path("logs") / "app.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            log_path = None

    # 获取根 logger
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # 清除现有 handlers
    logger.handlers.clear()

    # JSON 格式化器（用于文件日志）
    json_formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s',
        timestamp=True
    )

    # 文件 Handler（JSON 格式，带轮转）
    if log_path is not None:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(json_formatter)
        logger.addHandler(file_handler)

    # Console Handler（人类可读格式）
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 设置第三方库日志级别
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    logger.info(f"日志系统初始化完成，级别：{log_level}")


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 logger"""
    return logging.getLogger(name)
