"""
错误定义 - 统一错误格式和友好提示
"""
from fastapi import HTTPException, status


class ApiError(HTTPException):
    """HTTP error carrying the stable machine-readable API error code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict | None = None,
        user_message: str | None = None,
    ):
        self.code = code
        self.details = details or {}
        self.user_message = user_message or message
        super().__init__(
            status_code=status_code,
            detail={"message": message, "user_message": self.user_message, "code": code, "details": self.details},
            headers={"X-Error-Code": code},
        )


class EntitlementRequiredError(HTTPException):
    """权益要求错误"""

    def __init__(self, product_code: str):
        self.code = "ENTITLEMENT_REQUIRED"
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"此功能需要购买 {product_code} 权益",
            headers={"X-Error-Code": self.code},
        )


class ToolExecutionError(Exception):
    """Tool执行错误"""
    pass


class AgentLimitExceededError(Exception):
    """Agent限制超出错误"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class NotFoundError(HTTPException):
    """资源未找到错误"""

    def __init__(self, detail: str = "Resource not found"):
        self.code = "RESOURCE_NOT_FOUND"
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            headers={"X-Error-Code": self.code},
        )
