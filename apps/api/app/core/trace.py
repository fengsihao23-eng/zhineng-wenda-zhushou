"""
Trace & Audit - 全链路追踪和审计日志
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone
from uuid import UUID
from contextvars import ContextVar
from typing import Optional

from app.db.models.agent import (
    AgentRun as AgentRunModel,
    ToolCallLog as ToolCallLogModel,
    ModelUsageLog as ModelUsageLogModel
)
from app.db.models.trace import AuditLog as AuditLogModel
from app.db.models.user import User
from app.db.models.student import Student
from sqlalchemy import or_
from app.schemas.trace import (
    AgentRunCreate,
    AgentRunUpdate,
    AgentRunOut,
    AgentRunDetail,
    ToolCallLogCreate,
    ToolCallLogOut,
    ModelUsageLogCreate,
    AuditLogCreate,
    AuditLogOut
)


# 追踪上下文 - 用于在请求生命周期内传递追踪信息
class TraceContext:
    """追踪上下文"""
    def __init__(
        self,
        request_id: str,
        agent_run_id: UUID | None = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        student_id: UUID | None = None,
        school_id: UUID | None = None
    ):
        self.request_id = request_id
        self.agent_run_id = agent_run_id
        self.session_id = session_id
        self.user_id = user_id
        self.student_id = student_id
        self.school_id = school_id


# 上下文变量
trace_context: ContextVar[TraceContext | None] = ContextVar('trace_context', default=None)


class AgentRunTracer:
    """Agent运行追踪器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def start_run(self, data: AgentRunCreate) -> UUID:
        """
        开始Agent运行

        Args:
            data: Agent运行数据

        Returns:
            运行ID
        """
        run = AgentRunModel(
            session_id=data.session_id,
            school_id=data.school_id,
            student_id=data.student_id,
            query=data.query,
            intent=data.intent,
            entitlement_level=data.entitlement_level,
            status="running",
            created_at=datetime.now(timezone.utc)
        )

        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)

        return run.id

    async def finish_run(
        self,
        run_id: UUID,
        update_data: AgentRunUpdate
    ):
        """
        完成Agent运行

        Args:
            run_id: 运行ID
            update_data: 更新数据
        """
        values = update_data.model_dump(exclude_unset=True)
        if not values.get('finished_at'):
            values['finished_at'] = datetime.now(timezone.utc)

        await self.db.execute(
            update(AgentRunModel)
            .where(AgentRunModel.id == run_id)
            .values(**values)
        )
        await self.db.commit()

    async def get_run(self, run_id: UUID, school_id: UUID | None = None) -> Optional[AgentRunOut]:
        """
        获取Agent运行

        Args:
            run_id: 运行ID

        Returns:
            Agent运行或None
        """
        query = select(AgentRunModel).where(AgentRunModel.id == run_id)
        if school_id is not None:
            query = query.where(AgentRunModel.school_id == school_id)
        result = await self.db.execute(query)
        model = result.scalar_one_or_none()

        if model:
            return AgentRunOut.model_validate(model)
        return None

    async def get_run_detail(self, run_id: UUID, school_id: UUID | None = None) -> Optional[AgentRunDetail]:
        """
        获取Agent运行详情（包括Tool调用和模型使用）

        Args:
            run_id: 运行ID

        Returns:
            Agent运行详情或None
        """
        query = select(AgentRunModel).where(AgentRunModel.id == run_id)
        if school_id is not None:
            query = query.where(AgentRunModel.school_id == school_id)
        result = await self.db.execute(
            query
            .options(
                selectinload(AgentRunModel.tool_calls),
                selectinload(AgentRunModel.model_usage)
            )
        )
        model = result.scalar_one_or_none()

        if model:
            return AgentRunDetail.model_validate(model)
        return None

    async def list_runs(
        self,
        student_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        school_id: Optional[UUID] = None,
    ) -> list[AgentRunOut]:
        """
        列出Agent运行

        Args:
            student_id: 学生ID过滤
            session_id: 会话ID过滤
            status: 状态过滤
            limit: 返回数量
            offset: 偏移量

        Returns:
            Agent运行列表
        """
        query = select(AgentRunModel)

        if student_id:
            query = query.where(AgentRunModel.student_id == student_id)
        if session_id:
            query = query.where(AgentRunModel.session_id == session_id)
        if status:
            query = query.where(AgentRunModel.status == status)
        if school_id:
            query = query.where(AgentRunModel.school_id == school_id)

        query = query.order_by(
            AgentRunModel.created_at.desc()
        ).limit(limit).offset(offset)

        result = await self.db.execute(query)
        models = result.scalars().all()

        return [AgentRunOut.model_validate(m) for m in models]


class ToolCallTracer:
    """Tool调用追踪器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_tool_call(self, data: ToolCallLogCreate) -> UUID:
        """
        记录Tool调用

        Args:
            data: Tool调用数据

        Returns:
            日志ID
        """
        log = ToolCallLogModel(**data.model_dump())
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)

        return log.id

    async def get_tool_calls(self, agent_run_id: UUID) -> list[ToolCallLogOut]:
        """
        获取Agent运行的所有Tool调用

        Args:
            agent_run_id: Agent运行ID

        Returns:
            Tool调用列表
        """
        result = await self.db.execute(
            select(ToolCallLogModel)
            .where(ToolCallLogModel.agent_run_id == agent_run_id)
            .order_by(ToolCallLogModel.created_at)
        )
        models = result.scalars().all()

        return [ToolCallLogOut.model_validate(m) for m in models]


class ModelUsageTracer:
    """模型使用追踪器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_usage(self, data: ModelUsageLogCreate) -> UUID:
        """
        记录模型使用

        Args:
            data: 模型使用数据

        Returns:
            日志ID
        """
        log = ModelUsageLogModel(**data.model_dump())
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)

        return log.id


class AuditLogger:
    """审计日志记录器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record(self, data: AuditLogCreate) -> UUID:
        """
        记录审计日志

        Args:
            data: 审计日志数据

        Returns:
            日志ID
        """
        payload = data.model_dump(exclude_none=True)
        # AuditLog maps the database's ``metadata`` column to the Python
        # attribute ``extra_data`` because Declarative reserves ``metadata``.
        if "metadata" in payload:
            payload["extra_data"] = payload.pop("metadata")
        log = AuditLogModel(**payload)
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)

        return log.id

    async def list_logs(
        self,
        actor_id: Optional[UUID] = None,
        action: Optional[str] = None,
        allowed: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
        school_id: UUID | None = None,
    ) -> list[AuditLogOut]:
        """
        列出审计日志

        Args:
            actor_id: 执行者ID过滤
            action: 操作过滤
            allowed: 是否允许过滤
            limit: 返回数量
            offset: 偏移量

        Returns:
            审计日志列表
        """
        query = select(AuditLogModel)

        if school_id is not None:
            query = query.outerjoin(User, AuditLogModel.actor_id == User.id).outerjoin(
                Student, AuditLogModel.actor_id == Student.id
            ).where(or_(User.school_id == school_id, Student.school_id == school_id))

        if actor_id:
            query = query.where(AuditLogModel.actor_id == actor_id)
        if action:
            query = query.where(AuditLogModel.action == action)
        if allowed is not None:
            query = query.where(AuditLogModel.allowed == allowed)

        query = query.order_by(
            AuditLogModel.created_at.desc()
        ).limit(limit).offset(offset)

        result = await self.db.execute(query)
        models = result.scalars().all()

        return [AuditLogOut.model_validate(m) for m in models]
