"""
Tool Registry
"""
import logging
from typing import Optional

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Tool注册表"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        """注册Tool"""
        self._tools[tool.name] = tool
        logger.info(f"Tool registered: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        """获取Tool"""
        return self._tools.get(name)

    def list_for_entitlement(self, entitlement_level: str) -> list[dict]:
        """列出可用Tool（给模型看的Schema）"""
        available = []

        for tool in self._tools.values():
            # 检查权益要求
            if tool.required_entitlement:
                if tool.required_entitlement == "BASIC" and entitlement_level in {"BASIC", "DIAGNOSIS"}:
                    pass
                elif tool.required_entitlement != entitlement_level:
                    continue

            available.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            })

        return available

    def list_all_tools(self) -> list[BaseTool]:
        """列出所有Tool"""
        return list(self._tools.values())


# 全局单例
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取Tool Registry单例"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
