"""学生聊天 API。

第一阶段只提供学生本人范围内的成绩问答。会话 ID、消息 ID 和
Agent trace 都由服务端生成，客户端不能伪造数据范围。
"""
from __future__ import annotations

import json
import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.agent.agent_loop import AgentLoop
from app.api.deps import AuthenticatedStudent, get_current_student, get_db
from app.core.logging import get_logger
from app.core.prompt_registry import PromptRegistry
from app.core.errors import ApiError
from app.db.models.chat import ChatMessage, ChatSession
from app.db.models.trace import AuditLog
from app.db.models.platform import PlatformFeedback
from app.tools.init import init_tools
from app.tools.registry import ToolRegistry
from app.ai.gateway import get_model_gateway
from app.ai.gateway import ModelProviderUnavailableError

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class SessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class MessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    client_message_id: UUID | None = None


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    status: str = "completed"
    sources: list[dict[str, Any]] = Field(default_factory=list)
    agent_run_id: str | None = None


class SessionOut(BaseModel):
    id: str
    title: str | None
    status: str
    created_at: str
    updated_at: str
    message_count: int


class MessageResponse(BaseModel):
    session_id: str
    message: ChatMessageOut
    agent_run_id: str
    tools_called: int
    sources: list[dict[str, Any]] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    rating: str = Field(..., pattern="^(helpful|not_helpful|data_wrong|inappropriate)$")
    note: str | None = Field(default=None, max_length=500)


def _sse(event: str, data: dict[str, Any], request_id: str, seq: int) -> str:
    payload = {"request_id": request_id, "seq": seq, "data": data}
    return f"id: {seq}\nevent: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


async def _get_session(
    session_id: UUID,
    current_user: AuthenticatedStudent,
    db: AsyncSession,
) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.school_id == current_user.school_id,
            ChatSession.student_id == current_user.student_id,
            ChatSession.status == "active",
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在或无权访问",
            headers={"X-Error-Code": "SESSION_NOT_FOUND"},
        )
    return session


async def _history(session_id: UUID, db: AsyncSession) -> list[dict[str, str]]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
    )
    messages = result.scalars().all()
    return [{"role": item.role, "content": item.content} for item in reversed(messages)]


def _registry(db: AsyncSession) -> ToolRegistry:
    # Tool 实例持有数据库会话，不能使用跨请求的全局实例。
    registry = ToolRegistry()
    init_tools(db, registry)
    return registry


async def _run_agent(
    request: Request,
    current_user: AuthenticatedStudent,
    db: AsyncSession,
    content: str,
    session: ChatSession,
    history: list[dict[str, str]],
):
    agent = AgentLoop(
        db,
        _registry(db),
        get_model_gateway(),
        prompt_registry=PromptRegistry(db),
    )
    return await agent.run(
        user_query=content,
        student_id=current_user.student_id,
        school_id=current_user.school_id,
        user_id=current_user.user_id,
        request_id=getattr(request.state, "request_id", str(uuid4())),
        chat_history=history[:-1],
        session_id=session.id,
    )


async def _save_user_message(
    session: ChatSession,
    request_data: MessageCreateRequest,
    db: AsyncSession,
) -> tuple[ChatMessage, bool]:
    if request_data.client_message_id:
        existing_result = await db.execute(
            select(ChatMessage).where(ChatMessage.id == request_data.client_message_id)
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            if (
                existing.session_id != session.id
                or existing.role != "user"
                or existing.content != request_data.content.strip()
            ):
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "CLIENT_MESSAGE_ID_CONFLICT",
                    "client_message_id 已用于另一条消息",
                )
            return existing, False

    message = ChatMessage(
        id=request_data.client_message_id or uuid4(),
        session_id=session.id,
        role="user",
        content=request_data.content.strip(),
    )
    db.add(message)
    session.last_message_at = datetime.now(timezone.utc)
    session.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # A concurrent retry may have inserted the same client id between the
        # lookup and insert. Return that canonical row to preserve idempotency.
        if request_data.client_message_id:
            existing_result = await db.execute(
                select(ChatMessage).where(
                    ChatMessage.id == request_data.client_message_id,
                    ChatMessage.session_id == session.id,
                    ChatMessage.role == "user",
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing:
                return existing, False
        raise
    await db.refresh(message)
    return message, True


async def _existing_assistant(user_message: ChatMessage, db: AsyncSession) -> ChatMessage | None:
    if not user_message.agent_run_id:
        return None
    result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.session_id == user_message.session_id,
            ChatMessage.agent_run_id == user_message.agent_run_id,
            ChatMessage.role == "assistant",
        )
    )
    return result.scalar_one_or_none()


async def _find_idempotent_reply(
    session: ChatSession,
    request_data: MessageCreateRequest,
    db: AsyncSession,
) -> ChatMessage | None:
    """Return a completed reply for a retried client message, if available."""
    if request_data.client_message_id is None:
        return None
    result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.id == request_data.client_message_id,
            ChatMessage.session_id == session.id,
            ChatMessage.role == "user",
        )
    )
    existing_user = result.scalar_one_or_none()
    if existing_user is None:
        return None
    if existing_user.content != request_data.content.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="client_message_id 已用于另一条消息",
            headers={"X-Error-Code": "CLIENT_MESSAGE_ID_CONFLICT"},
        )
    if existing_user.agent_run_id is None:
        return None
    reply_result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.session_id == session.id,
            ChatMessage.role == "assistant",
            ChatMessage.agent_run_id == existing_user.agent_run_id,
        ).order_by(ChatMessage.created_at.desc()).limit(1)
    )
    return reply_result.scalar_one_or_none()


def _message_response(session: ChatSession, assistant: ChatMessage, sources: list[dict[str, Any]] | None = None) -> MessageResponse:
    return MessageResponse(
        session_id=str(session.id),
        message=ChatMessageOut(
            id=str(assistant.id),
            role="assistant",
            content=assistant.content,
            created_at=assistant.created_at.isoformat(),
            sources=sources or [],
            agent_run_id=str(assistant.agent_run_id) if assistant.agent_run_id else None,
        ),
        agent_run_id=str(assistant.agent_run_id) if assistant.agent_run_id else "",
        tools_called=0,
        sources=sources or [],
    )


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: SessionCreateRequest | None = None,
    current_user: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    session = ChatSession(
        school_id=current_user.school_id,
        student_id=current_user.student_id,
        title=(data.title if data else None),
        status="active",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionOut(
        id=str(session.id),
        title=session.title,
        status=session.status,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        message_count=0,
    )


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    current_user: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession, func.count(ChatMessage.id))
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(
            ChatSession.school_id == current_user.school_id,
            ChatSession.student_id == current_user.student_id,
            ChatSession.status == "active",
        )
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
        .limit(50)
    )
    return [
        SessionOut(
            id=str(session.id),
            title=session.title,
            status=session.status,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            message_count=int(count),
        )
        for session, count in result.all()
    ]


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def get_session_messages(
    session_id: UUID,
    current_user: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    await _get_session(session_id, current_user, db)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return [
        ChatMessageOut(
            id=str(message.id),
            role=message.role,
            content=message.content,
            created_at=message.created_at.isoformat(),
            agent_run_id=str(message.agent_run_id) if message.agent_run_id else None,
        )
        for message in result.scalars().all()
    ]


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
async def send_message(
    session_id: UUID,
    data: MessageCreateRequest,
    request: Request,
    current_user: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session(session_id, current_user, db)
    existing = await _find_idempotent_reply(session, data, db)
    if existing is not None:
        return _message_response(session, existing)
    user_message, created = await _save_user_message(session, data, db)
    if not created:
        raise ApiError(status.HTTP_409_CONFLICT, "MESSAGE_IN_PROGRESS", "消息正在处理中，请稍后重试")
    history = await _history(session.id, db)
    try:
        result = await _run_agent(request, current_user, db, data.content, session, history)
    except Exception:
        # The user row was committed before the model call. Remove an
        # unassociated row so a retry with the same client_message_id is
        # allowed after a failed run.
        await db.rollback()
        await db.execute(
            ChatMessage.__table__.delete().where(ChatMessage.id == user_message.id)
        )
        await db.commit()
        raise
    user_message.agent_run_id = UUID(result.agent_run_id)

    assistant = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=result.final_answer,
        agent_run_id=UUID(result.agent_run_id),
    )
    session.last_message_at = datetime.now(timezone.utc)
    db.add(assistant)
    await db.commit()
    await db.refresh(assistant)
    sources = getattr(result, "sources", [])
    return MessageResponse(
        session_id=str(session.id),
        message=ChatMessageOut(
            id=str(assistant.id),
            role="assistant",
            content=assistant.content,
            created_at=assistant.created_at.isoformat(),
            sources=sources,
            agent_run_id=result.agent_run_id,
        ),
        agent_run_id=result.agent_run_id,
        tools_called=result.total_tools_called,
        sources=sources,
    )


@router.post("/sessions/{session_id}/stream")
async def stream_message(
    session_id: UUID,
    data: MessageCreateRequest,
    request: Request,
    current_user: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session(session_id, current_user, db)
    existing = await _find_idempotent_reply(session, data, db)
    if existing is None:
        user_message, created = await _save_user_message(session, data, db)
        if not created:
            user_message = None
            in_progress = True
        else:
            in_progress = False
    else:
        user_message = None
        in_progress = False
    history = await _history(session.id, db)
    request_id = getattr(request.state, "request_id", str(uuid4()))

    async def event_generator():
        seq = 1
        assistant_committed = False
        try:
            if existing is not None:
                yield _sse(
                    "message_start",
                    {"session_id": str(session.id), "message_id": str(existing.id)},
                    request_id,
                    seq,
                )
                seq += 1
                yield _sse("content_delta", {"content": existing.content}, request_id, seq)
                seq += 1
                yield _sse(
                    "message_end",
                    {"message_id": str(existing.id), "agent_run_id": str(existing.agent_run_id)},
                    request_id,
                    seq,
                )
                seq += 1
                yield _sse("done", {"session_id": str(session.id), "resumed": True}, request_id, seq)
                return
            if in_progress:
                yield _sse(
                    "error",
                    {"code": "MESSAGE_IN_PROGRESS", "message": "消息正在处理中，请稍后重试"},
                    request_id,
                    seq,
                )
                return
            if await request.is_disconnected():
                return
            yield _sse(
                "message_start",
                {"session_id": str(session.id), "message_id": str(user_message.id)},
                request_id,
                seq,
            )
            seq += 1
            result = await _run_agent(request, current_user, db, data.content, session, history)
            if user_message is not None:
                user_message.agent_run_id = UUID(result.agent_run_id)
            sources = getattr(result, "sources", [])
            for step in getattr(result, "steps", []):
                yield _sse(
                    "tool_call_start",
                    {"tool_name": step.tool_name, "arguments": step.tool_args or {}},
                    request_id,
                    seq,
                )
                seq += 1
                yield _sse(
                    "tool_call_end",
                    {"tool_name": step.tool_name, "ok": bool(step.tool_result and step.tool_result.get("ok"))},
                    request_id,
                    seq,
                )
                seq += 1
            for source in sources:
                yield _sse("source", source, request_id, seq)
                seq += 1
            yield _sse("content_delta", {"content": result.final_answer}, request_id, seq)
            seq += 1

            assistant = ChatMessage(
                session_id=session.id,
                role="assistant",
                content=result.final_answer,
                agent_run_id=UUID(result.agent_run_id),
            )
            session.last_message_at = datetime.now(timezone.utc)
            db.add(assistant)
            await db.commit()
            await db.refresh(assistant)
            assistant_committed = True
            yield _sse(
                "message_end",
                {"message_id": str(assistant.id), "agent_run_id": result.agent_run_id},
                request_id,
                seq,
            )
            seq += 1
            yield _sse("done", {"session_id": str(session.id)}, request_id, seq)
        except Exception as exc:
            logger.exception("chat stream failed", extra={"request_id": request_id})
            await db.rollback()
            if user_message is not None and not assistant_committed:
                await db.execute(
                    ChatMessage.__table__.delete().where(ChatMessage.id == user_message.id)
                )
                await db.commit()
            if isinstance(exc, ModelProviderUnavailableError):
                yield _sse("error", {"code": "MODEL_PROVIDER_NOT_CONFIGURED", "message": str(exc)}, request_id, seq)
            else:
                yield _sse("error", {"code": "CHAT_FAILED", "message": "暂时无法生成回答，请稍后重试"}, request_id, seq)
        except asyncio.CancelledError:
            # A browser-side AbortController closes the stream with task
            # cancellation. Remove only an unassociated user row so a retry
            # with the same client_message_id can safely resume.
            await db.rollback()
            if user_message is not None and not assistant_committed:
                await db.execute(
                    ChatMessage.__table__.delete().where(ChatMessage.id == user_message.id)
                )
                await db.commit()
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_session(
    session_id: UUID,
    current_user: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session(session_id, current_user, db)
    session.status = "archived"
    await db.commit()


@router.post("/messages/{message_id}/feedback", status_code=status.HTTP_202_ACCEPTED)
async def submit_feedback(
    message_id: UUID,
    data: FeedbackRequest,
    current_user: AuthenticatedStudent = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(
            ChatMessage.id == message_id,
            ChatSession.school_id == current_user.school_id,
            ChatSession.student_id == current_user.student_id,
        )
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="消息不存在或无权访问",
            headers={"X-Error-Code": "MESSAGE_NOT_FOUND"},
        )
    db.add(
        AuditLog(
            action="message_feedback",
            actor_type="student",
            actor_id=current_user.user_id,
            resource_type="chat_message",
            resource_id=message_id,
            allowed=True,
            reason=data.rating,
            extra_data={"note": data.note} if data.note else None,
        )
    )
    # Keep the original audit record for traceability and create an actionable
    # operations item so school/city teams can triage feedback in one queue.
    db.add(
        PlatformFeedback(
            school_id=current_user.school_id,
            user_id=current_user.user_id,
            student_id=current_user.student_id,
            message_id=message_id,
            rating=data.rating,
            category="回答质量",
            note=data.note,
        )
    )
    await db.commit()
    return {"accepted": True}
