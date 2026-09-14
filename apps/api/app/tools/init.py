"""
Tool初始化和注册
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.registry import ToolRegistry
from app.tools.exam_tools import GetExamSummaryTool
from app.tools.score_tools import GetSubjectScoresTool, GetRankingChangeTool
from app.tools.analysis_tools import GetScoreTrendTool, GetQuestionLossTool, GetDiagnosisTool


def init_tools(db: AsyncSession, registry: ToolRegistry):
    """初始化所有Tools"""

    # 考试相关
    registry.register(GetExamSummaryTool(db))

    # 成绩相关
    registry.register(GetSubjectScoresTool(db))
    registry.register(GetRankingChangeTool(db))

    # 分析相关
    registry.register(GetScoreTrendTool(db))
    registry.register(GetQuestionLossTool(db))
    registry.register(GetDiagnosisTool(db))
