"""Immutable answer facts and duplicate-safe per-message feedback."""
from uuid import uuid4
import pytest
from sqlalchemy import select,func,update
from app.db.models import StudentSubjectScore
from app.db.models.platform import PlatformFeedback
from test_education_workbench import actors,setup_exam,add_scores,P


@pytest.mark.asyncio
async def test_answer_evidence_stays_pinned_and_feedback_has_durable_readback(client,test_db,actors):
    exam=await setup_exam(client,actors)
    await add_scores(test_db,actors,exam)
    actors['switch']('student')
    session=(await client.post('/api/v1/chat/sessions',json={})).json()['id']
    result=await client.post(f'/api/v1/chat/sessions/{session}/messages',json={'content':'数学多少分','client_message_id':str(uuid4())})
    assert result.status_code==200,result.text
    message_id=result.json()['message']['id']
    await test_db.execute(update(StudentSubjectScore).where(StudentSubjectScore.student_id == actors['student'].id).values(score=91))
    await test_db.commit()
    source=await client.get(P+f'/evidence/{message_id}/0')
    assert source.json()['captured_source']['facts']['score']==80
    assert (await client.get(f'/api/v1/chat/messages/{message_id}/feedback')).json()=={'feedback':None}
    key=str(uuid4());path=f'/api/v1/chat/messages/{message_id}/feedback'
    one=await client.post(path,json={'rating':'helpful'},headers={'Idempotency-Key':key})
    two=await client.post(path,json={'rating':'helpful'},headers={'Idempotency-Key':key})
    three=await client.post(path,json={'rating':'helpful'},headers={'Idempotency-Key':str(uuid4())})
    assert one.status_code==two.status_code==three.status_code==202
    assert one.json()['id']==two.json()['id']==three.json()['id']
    assert await test_db.scalar(select(func.count()).select_from(PlatformFeedback))==1
    assert (await client.get(path)).json()['feedback']['rating']=='helpful'
    assert (await client.post(path,json={'rating':'data_wrong'})).status_code==409
    actors['switch']('foreign')
    assert (await client.get(path)).status_code==403
