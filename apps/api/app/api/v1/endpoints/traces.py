"""
Admin API - Trace查询
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.database import get_db
from app.api.deps import require_admin, AuthenticatedUser
from app.core.trace import AgentRunTracer, AuditLogger
from app.schemas.trace import AgentRunOut, AgentRunDetail, AuditLogOut

router = APIRouter(
    prefix="/traces",
    tags=["traces"],
    dependencies=[Depends(require_admin)],
)


@router.get("/runs/{run_id}", response_model=AgentRunDetail)
async def get_agent_run(
    run_id: UUID,
    current_user: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取Agent运行详情"""
    tracer = AgentRunTracer(db)
    scope = None if current_user.has_role("SUPER_ADMIN") else current_user.school_id
    detail = await tracer.get_run_detail(run_id, school_id=scope)

    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent run not found",
            headers={"X-Error-Code": "AGENT_RUN_NOT_FOUND"},
        )

    return detail


@router.get("/runs", response_model=list[AgentRunOut])
async def list_agent_runs(
    student_id: UUID | None = None,
    session_id: UUID | None = None,
    status: str | None = None,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """列出Agent运行"""
    tracer = AgentRunTracer(db)
    scope = None if current_user.has_role("SUPER_ADMIN") else current_user.school_id
    runs = await tracer.list_runs(
        student_id=student_id,
        session_id=session_id,
        status=status,
        limit=limit,
        offset=offset,
        school_id=scope,
    )
    return runs


@router.get("/audit", response_model=list[AuditLogOut])
async def list_audit_logs(
    actor_id: UUID | None = None,
    action: str | None = None,
    allowed: bool | None = None,
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """列出审计日志"""
    audit_logger = AuditLogger(db)
    # AuditLog currently has no school_id column; scope through actor users for
    # school admins and leave global visibility only to SUPER_ADMIN.
    scope = None if current_user.has_role("SUPER_ADMIN") else current_user.school_id
    logs = await audit_logger.list_logs(
        actor_id=actor_id,
        action=action,
        allowed=allowed,
        limit=limit,
        offset=offset,
        school_id=scope,
    )
    return logs
