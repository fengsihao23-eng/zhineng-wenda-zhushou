"""School prompt and mini program endpoints. No browser supplied data or role is trusted."""
from typing import Literal
from uuid import UUID
from urllib.parse import quote
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_db
from app.services import answer_workbench as service
from app.api.v1.endpoints.education import write

router = APIRouter(prefix='/answer-workbench', tags=['answer-workbench'])


class Payload(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Draft(Payload):
    draft: dict = Field(max_length=40)

    @field_validator('draft')
    @classmethod
    def validate_draft(cls, value):
        for key in ['content', 'format', 'reason', 'customProhibited', 'boundaryMessage']:
            if key in value and (not isinstance(value[key], str) or len(value[key]) > 30000):
                raise ValueError('草稿内容应为不超过30000字的文本')
        for key in ['topics', 'prohibitions']:
            if key in value and (not isinstance(value[key], list) or len(value[key]) > 20 or any(not isinstance(v, str) for v in value[key])):
                raise ValueError('维护选项格式不正确')
        return value
    expected: int = Field(ge=1)


class Restore(Payload):
    version_id: str
    expected: int = Field(ge=1)


class Trial(Payload):
    user_id: UUID
    draft_id: str
    draft_revision: int = Field(ge=1)
    roles: list[str] = Field(min_length=1, max_length=7)
    question: str = Field(min_length=1, max_length=1500)
    kind: Literal['authorized', 'limited', 'unauthorized', 'missing']
    test_stage: Literal['小学', '初中', '高中']


class Review(Payload):
    accepted: bool
    note: str = Field(default='', max_length=2000)


class Publish(Payload):
    expected: int = Field(ge=1)
    preview_hash: str = Field(min_length=64, max_length=64)


class Question(Payload):
    question: str = Field(min_length=1, max_length=1500)
    session_id: UUID | None = None

    @field_validator('question')
    @classmethod
    def clean(cls, value):
        if not value.strip():
            raise ValueError('请填写问题')
        return value.strip()


class Ticket(Question):
    question: str = Field(min_length=1, max_length=2000)
    message_ids: list[str] = Field(default_factory=list, max_length=6)
    feedback_message_id: UUID | None = None


class TicketAction(Payload):
    expected: int = Field(ge=1)
    question: str = Field(default='', max_length=2000)
    text: str = Field(default='', max_length=4000)
    reply_kind: Literal['data', 'insufficient', 'permission', 'routing'] = 'data'
    reviewed: bool = False
    session_id: UUID | None = None
    message_ids: list[str] = Field(default_factory=list, max_length=6)
    sources: list[dict] = Field(default_factory=list, max_length=100)


class Sources(Payload):
    sources: list[dict] = Field(max_length=100)
    user_id: UUID | None = None


@router.get('/admin/state')
async def state(actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    return await service.state(db, actor)


@router.post('/admin/scopes/{scope}/draft')
async def draft(scope: str, body: Draft, actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    return await write(db, service.save_draft(db, actor, scope, body.model_dump()))


@router.post('/admin/scopes/{scope}/restore')
async def restore(scope: str, body: Restore, actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    return await write(db, service.restore(db, actor, scope, body.model_dump()))


@router.post('/admin/scopes/{scope}/trials')
async def trial(scope: str, body: Trial, key: UUID=Header(alias='Idempotency-Key'), actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    return await write(db, service.run_trial(db, actor, scope, body, key))


@router.post('/admin/trials/{rid}/review')
async def review(rid: UUID, body: Review, actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    return await write(db, service.review_trial(db, actor, rid, body))


@router.post('/admin/scopes/{scope}/preview')
async def preview(scope: str, actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    service.require_manager(actor)
    return await service.publish_readiness(db, actor, scope)


@router.post('/admin/scopes/{scope}/publish')
async def publish(scope: str, body: Publish, key: UUID=Header(alias='Idempotency-Key'), actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    return await write(db, service.publish(db, actor, scope, body, key))


@router.get('/mini/state')
async def mini(actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    return await service.mini_state(db, actor)


@router.post('/mini/ask')
async def ask(body: Question, key: UUID=Header(alias='Idempotency-Key'), actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    return await write(db, service.ask(db, actor, body, key))


@router.get('/tickets')
async def tickets(management: bool=False, actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    return await service.tickets_list(db, actor, management)


@router.post('/tickets')
async def ticket_create(body: Ticket, key: UUID=Header(alias='Idempotency-Key'), actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    return await write(db, service.ticket_create(db, actor, body, key))


@router.get('/tickets/{rid}')
async def ticket(rid: UUID, management: bool=False, actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    return await service.ticket_view(db, actor, await service.ticket_get(db, actor, rid, management), management)


@router.post('/tickets/{rid}/{action}')
async def ticket_action(rid: UUID, action: Literal['claim', 'query', 'draft', 'reply', 'append', 'close', 'read'], body: TicketAction,
    key: UUID=Header(alias='Idempotency-Key'), actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    return await write(db, service.ticket_action(db, actor, rid, action, body, key))


@router.post('/sources/inspect')
async def inspect(body: Sources, actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    return await service.inspect_sources(db, actor, body)


@router.get('/reports/{rid}/file')
async def report_file(rid: UUID, version: int=Query(ge=1), page: int | None=Query(default=None, ge=1, le=100), download: bool=False,
    user_id: UUID | None=None, actor=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    info = None
    if user_id:
        service.require_manager(actor)
        info = await service.person(db, actor, user_id)
    content, filename = await service.report_access(db, actor, rid, version, page, download, info)
    return Response(content, media_type='image/png' if page else 'application/pdf', headers={'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff', **({'Content-Disposition': "attachment; filename*=UTF-8''"+quote(filename)} if not page else {})})
