"""Quota and traffic acceptance against both SQLite and isolated PostgreSQL."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4, UUID
from types import SimpleNamespace
import pytest
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.db.models import User
from app.db.models.answer_workbench import AnswerDailyUsage, AnswerPresence, AnswerSession
from app.db.models.operation_receipt import OperationReceipt
from app.services import answer_capacity as capacity, answer_workbench as service
from app.api.deps import AuthenticatedUser
from test_answer_workbench import setup, actors, exam_people, post  # noqa: F401
from test_exam_management import switch

ROOT='/api/v1/answer-workbench'


def student_actor(actors):
    return AuthenticatedUser(actors['student'].user_id,actors['school'].id,'student',['STUDENT'])


@pytest.mark.asyncio
async def test_last_question_is_shared_and_idempotent_and_reports_tickets_remain(client,test_db,actors,setup):
    switch(actors,test_db,'student')
    actor=student_actor(actors)
    test_db.add(AnswerDailyUsage(school_id=actor.school_id,user_id=actor.user_id,day=capacity.day_at(),used=99))
    await test_db.commit()
    status=(await client.get(ROOT+'/mini/status')).json()
    assert status['quota']['remaining']==1
    key=uuid4();body={'question':'我的数学成绩'}
    answer=await post(client,'/mini/ask',body,key=key)
    assert answer['questionStatus']['quota']['remaining']==0
    assert (await post(client,'/mini/ask',body,key=key))==answer
    denied=await client.post(ROOT+'/mini/ask',json=body,headers={'Idempotency-Key':str(uuid4())})
    assert denied.status_code==429 and denied.json()['error']['code']=='DAILY_QUESTION_LIMIT'
    assert denied.json()['error']['details']['quota']['used']==100
    assert (await client.get(ROOT+'/mini/state')).json()['questionStatus']['quota']['remaining']==0
    assert (await post(client,'/tickets',{'question':'额度用尽后仍能留言'}))['status']=='待处理'
    assert await test_db.scalar(select(func.count()).select_from(AnswerSession))==1
    switch(actors,test_db,'teacher')
    assert (await client.get(ROOT+'/mini/status')).json()['quota']['remaining']==100
    # Client-supplied remaining counts cannot override the server.
    await post(client,'/mini/ask',{'question':'你好','remaining':100},422)


@pytest.mark.asyncio
async def test_failures_refund_and_rollback_receipts_but_boundary_answers_count(client,test_db,actors,setup,monkeypatch):
    switch(actors,test_db,'student')
    async def broken(**kwargs):raise RuntimeError('synthetic outage')
    monkeypatch.setattr(service,'get_model_gateway',lambda:SimpleNamespace(chat=broken))
    key=uuid4();body={'question':'我的数学成绩'}
    answer=await post(client,'/mini/ask',body,key=key)
    assert answer['messages'][-1]['serviceFailure']
    assert answer['questionStatus']['quota']['remaining']==100
    assert await post(client,'/mini/ask',body,key=key)==answer
    denied=await post(client,'/mini/ask',{'question':'查询其他同学的成绩'})
    assert denied['messages'][-1]['fallback'] and denied['questionStatus']['quota']['used']==1
    before=await test_db.scalar(select(func.count()).select_from(OperationReceipt))
    async def fail(*args,**kwargs):raise RuntimeError('transaction failed before saving')
    monkeypatch.setattr(service,'evaluate',fail)
    from app.main import app
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://test') as other:
        response=await other.post(ROOT+'/mini/ask',json=body,headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==500
    assert await test_db.scalar(select(func.count()).select_from(OperationReceipt))==before
    assert (await client.get(ROOT+'/mini/status')).json()['quota']['used']==1


@pytest.mark.asyncio
async def test_shanghai_midnight_resets_and_previous_day_refund_stays_on_previous_day(client,test_db,actors,setup,monkeypatch):
    switch(actors,test_db,'student');actor=student_actor(actors)
    before=datetime(2026,10,20,15,59,59,tzinfo=timezone.utc)
    monkeypatch.setattr(capacity,'now',lambda:before)
    test_db.add(AnswerDailyUsage(school_id=actor.school_id,user_id=actor.user_id,day=capacity.day_at(),used=100));await test_db.commit()
    assert (await capacity.quota(test_db,actor))['remaining']==0
    monkeypatch.setattr(capacity,'now',lambda:before+timedelta(seconds=1))
    next_day=await capacity.quota(test_db,actor)
    assert next_day['remaining']==100 and next_day['date']=='2026-10-21'
    assert next_day['resetAt']=='2026-10-22T00:00:00+08:00'
    await capacity.reserve(test_db,actor)
    await capacity.release(test_db,actor,before.astimezone(capacity.SHANGHAI).date());await test_db.commit()
    assert (await capacity.quota(test_db,actor))['used']==1


@pytest.mark.parametrize('count,level',[(0,None),(499,None),(500,'busy'),(999,'busy'),(1000,'extreme'),(1001,'extreme')])
def test_congestion_boundaries(count,level):
    value=capacity.congestion(count)
    assert value['level']==level
    assert bool(value['label'])==bool(level)


@pytest.mark.asyncio
async def test_presence_deduplicates_people_and_expires_across_clients_and_disabled_accounts(client,test_db,actors,setup,monkeypatch):
    switch(actors,test_db,'student');actor=student_actor(actors)
    instant=datetime(2026,10,20,10,tzinfo=timezone.utc)
    monkeypatch.setattr(capacity,'now',lambda:instant)
    clients=[uuid4(),uuid4()]
    for key in clients:
        value=await post(client,'/mini/presence',{'client_id':str(key)})
        assert value['traffic']['count']==1
    value=await post(client,'/mini/presence',{'client_id':str(clients[0]),'present':False})
    assert value['traffic']['count']==1
    switch(actors,test_db,'teacher')
    value=await post(client,'/mini/presence',{'client_id':str(uuid4())})
    assert value['traffic']['count']==2
    user=await test_db.get(User,actor.user_id);user.status='disabled';await test_db.commit()
    assert (await client.get(ROOT+'/mini/status')).json()['traffic']['count']==1
    user.status='active';await test_db.commit()
    monkeypatch.setattr(capacity,'now',lambda:instant+timedelta(seconds=91))
    assert (await client.get(ROOT+'/mini/status')).json()['traffic']['count']==0


@pytest.mark.asyncio
async def test_parallel_workers_cannot_exceed_last_slot(client,test_engine,test_db,actors):
    if test_engine.dialect.name!='postgresql':pytest.skip('Separate connections require the isolated PostgreSQL test gate')
    actor=student_actor(actors)
    test_db.add(AnswerDailyUsage(school_id=actor.school_id,user_id=actor.user_id,day=capacity.day_at(),used=99));await test_db.commit()
    sessions=async_sessionmaker(test_engine,expire_on_commit=False)
    async def attempt():
        async with sessions() as db:
            try:
                await capacity.reserve(db,actor);await db.commit();return True
            except Exception as error:
                await db.rollback();assert getattr(error,'code',None)=='DAILY_QUESTION_LIMIT';return False
    results=await asyncio.gather(*(attempt() for _ in range(10)))
    assert results.count(True)==1
    assert (await capacity.quota(test_db,actor))['used']==100


@pytest.mark.asyncio
async def test_signed_accounts_on_same_school_network_get_separate_rate_buckets(client,test_db,actors,setup,monkeypatch):
    from app.core.rate_limit import RateLimiter
    from app.core.security import create_access_token
    monkeypatch.setattr('app.main.rate_limiter',RateLimiter(1,100))
    def headers(uid):
        token=create_access_token({'sub':str(uid),'school_id':str(actors['school'].id)})
        return {'Authorization':'Bearer '+token,'X-Real-IP':'192.0.2.10'}
    first=await client.get(ROOT+'/admin/state',headers=headers(actors['admin'].id))
    assert first.status_code==200
    other=await client.get(ROOT+'/admin/state',headers=headers(actors['teacher'].id))
    assert other.status_code==200
    repeat=await client.get(ROOT+'/admin/state',headers=headers(actors['admin'].id))
    assert repeat.status_code==429


@pytest.mark.asyncio
async def test_missing_configuration_does_not_charge(client,test_db,actors,setup,monkeypatch):
    switch(actors,test_db,'student')
    async def missing(*args,**kwargs):return {'limits':None,'prompts':{}}
    monkeypatch.setattr(service,'bundle',missing)
    result=await post(client,'/mini/ask',{'question':'你好'})
    assert result['messages'][-1]['configurationFailure']
    assert result['questionStatus']['quota']['used']==0


@pytest.mark.asyncio
async def test_real_presence_thresholds_from_database(client,test_db,actors,setup):
    switch(actors,test_db,'student')
    school=actors['school'].id
    users=[{'id':uuid4(),'school_id':school,'username':'presence-'+uuid4().hex,'password_hash':'unused','status':'active'} for _ in range(1001)]
    await test_db.execute(User.__table__.insert(),users)
    records=[{'school_id':school,'user_id':user['id'],'client_id':uuid4(),'expires_at':capacity.now()+timedelta(seconds=90)} for user in users]
    await test_db.execute(AnswerPresence.__table__.insert(),records);await test_db.commit()
    for count,level in [(1001,'extreme'),(1000,'extreme'),(999,'busy'),(500,'busy'),(499,None)]:
        await test_db.execute(delete(AnswerPresence).where(AnswerPresence.user_id.in_([user['id'] for user in users[count:]])))
        await test_db.commit()
        status=(await client.get(ROOT+'/mini/status')).json()
        assert status['traffic']['count']==count and status['traffic']['level']==level
