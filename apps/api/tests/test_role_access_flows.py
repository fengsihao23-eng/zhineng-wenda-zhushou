"""Real authentication for school readers and staff with concurrent duties."""
import secrets
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio

from app.core.security import get_password_hash
from app.db.models import (User, Role, UserRole, Student, ImportedClass, Subject, TeachingAssignment,
                           HumanHandoff, PlatformFeedback, RiskEvent, School)


@pytest_asyncio.fixture
async def access_users(client, test_db, sample_school_id):
    password = secrets.token_urlsafe(24)
    password_hash = get_password_hash(password)
    roles = {}
    for code in ['SCHOOL_VIEWER', 'TEACHER', 'STUDENT', 'SUPER_ADMIN', 'PRINCIPAL']:
        role = Role(id=uuid4(), code=code, name=code)
        test_db.add(role); roles[code] = role
    classrooms = [ImportedClass(id=uuid4(), school_id=sample_school_id, external_class_id=str(i), name=f'QA class {i}', source_system='native') for i in [1, 2]]
    subject = Subject(id=uuid4(), school_id=sample_school_id, code='ROLE-MATH', name='数学', source_system='native')
    test_db.add_all([*classrooms, subject]); await test_db.flush()
    people = {}
    for key, codes in [('viewer', ['SCHOOL_VIEWER']), ('mixed', ['TEACHER', 'PRINCIPAL', 'SCHOOL_VIEWER']),
                       ('student', ['STUDENT']), ('outside', ['STUDENT']), ('super', ['SUPER_ADMIN'])]:
        user = User(id=uuid4(), school_id=sample_school_id, username=f'role-qa-{key}-{uuid4().hex[:8]}',
                    display_name=f'Synthetic {key}', password_hash=password_hash, status='active')
        test_db.add(user); await test_db.flush()
        for code in codes:
            test_db.add(UserRole(school_id=sample_school_id, user_id=user.id, role_id=roles[code].id))
        people[key] = SimpleNamespace(user=user)
        if 'STUDENT' in codes:
            student = Student(id=uuid4(), school_id=sample_school_id, user_id=user.id, name=f'Synthetic {key}',
                              class_id=classrooms[1 if key == 'outside' else 0].id, status='active',
                              profile_fields={'年级': '高中一年级'})
            test_db.add(student); people[key].student = student; people[key].student_id = str(student.id)
    await test_db.flush()
    test_db.add(TeachingAssignment(school_id=sample_school_id, teacher_user_id=people['mixed'].user.id,
        class_id=classrooms[0].id, subject_id=subject.id, starts_at=datetime.now(timezone.utc)-timedelta(days=1)))
    for key in ['student', 'outside']:
        ticket = HumanHandoff(id=uuid4(), school_id=sample_school_id, student_id=people[key].student.id,
            reason='Synthetic request', summary='Synthetic student help', status='accepted', assigned_to=people['mixed'].user.id)
        test_db.add(ticket); people[key].handoff = ticket; people[key].handoff_id = str(ticket.id)
    feedback = PlatformFeedback(id=uuid4(), school_id=sample_school_id, user_id=people['student'].user.id,
        student_id=people['student'].student.id, rating='not_helpful', category='QA')
    risk = RiskEvent(id=uuid4(), school_id=sample_school_id, student_id=people['student'].student.id,
        event_type='QA', title='Synthetic risk', detail='Synthetic detail')
    test_db.add_all([feedback, risk]); await test_db.commit()
    for person in people.values():
        login = await client.post('/api/v1/auth/login', json={'username': person.user.username, 'password': password})
        assert login.status_code == 200
        person.headers = {'Authorization': 'Bearer '+login.json()['access_token']}
    return SimpleNamespace(**people, feedback=feedback, risk=risk, feedback_id=str(feedback.id), risk_id=str(risk.id))


@pytest.mark.asyncio
async def test_school_reader_can_read_queues_details_but_cannot_change_data(client, test_db, access_users):
    users = access_users
    for path in ['overview', 'students', 'feedback', 'risks', 'handoffs']:
        response = await client.get('/api/v1/platform/management/'+path, headers=users.viewer.headers)
        assert response.status_code == 200, response.text
        if path in {'feedback', 'risks', 'handoffs'}:
            assert all(not item.get('allowed_transitions') for item in response.json())
    own = await client.get('/api/v1/platform/management/students/'+users.student.student_id, headers=users.viewer.headers)
    assert own.status_code == 200
    detail = await client.get('/api/v1/platform/education/handoffs/'+users.student.handoff_id, headers=users.viewer.headers)
    assert detail.status_code == 200 and not detail.json()['can_reply']
    for kind, item in [('feedback', users.feedback), ('risks', users.risk), ('handoffs', users.student.handoff)]:
        response = await client.patch(f'/api/v1/platform/management/{kind}/{item.id}', headers=users.viewer.headers,
                                      json={'status': 'resolved', 'resolution': 'Must remain read only', 'expected_version': 1})
        assert response.status_code == 403 and response.headers['x-error-code'] == 'SCHOOL_READ_ONLY'
    other_school = School(id=uuid4(), name='Other school', code='OTHER-'+uuid4().hex)
    test_db.add(other_school); await test_db.flush()
    foreign = Student(id=uuid4(), school_id=other_school.id, name='Other school student', status='active')
    test_db.add(foreign); await test_db.commit()
    response = await client.get('/api/v1/platform/management/students/'+str(foreign.id), headers=users.viewer.headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_teacher_reader_can_reply_and_finish_own_scope_but_cannot_handle_other_students(client, access_users):
    users = access_users
    own = '/api/v1/platform/education/handoffs/'+users.student.handoff_id
    outside = '/api/v1/platform/education/handoffs/'+users.outside.handoff_id
    assert (await client.get(own, headers=users.mixed.headers)).json()['can_reply']
    outside_detail = await client.get(outside, headers=users.mixed.headers)
    assert outside_detail.status_code == 200 and not outside_detail.json()['can_reply']
    reply = await client.post(own+'/messages', headers={**users.mixed.headers, 'Idempotency-Key': str(uuid4())},
                              json={'content': 'Teacher reply within assigned class'})
    assert reply.status_code == 200, reply.text
    response = await client.post(outside+'/messages', headers={**users.mixed.headers, 'Idempotency-Key': str(uuid4())},
                                 json={'content': 'Must not reach this student'})
    assert response.status_code == 404
    response = await client.patch('/api/v1/platform/management/handoffs/'+users.outside.handoff_id,
        headers=users.mixed.headers, json={'status': 'resolved', 'resolution': 'Out of scope', 'expected_version': 1})
    assert response.status_code == 404
    response = await client.patch('/api/v1/platform/management/handoffs/'+users.student.handoff_id,
        headers=users.mixed.headers, json={'status': 'resolved', 'resolution': 'Followed up with student', 'expected_version': 1})
    assert response.status_code == 200, response.text
    response = await client.patch('/api/v1/platform/management/feedback/'+users.feedback_id,
        headers=users.mixed.headers, json={'status': 'resolved', 'resolution': 'Still read only', 'expected_version': 1})
    assert response.status_code == 403 and response.headers['x-error-code'] == 'SCHOOL_READ_ONLY'
    listed = (await client.get('/api/v1/platform/management/handoffs', headers=users.mixed.headers)).json()
    assert not next(item for item in listed if item['id'] == users.outside.handoff_id)['allowed_transitions']


@pytest.mark.asyncio
async def test_answer_tickets_preserve_read_scope_and_restrict_mixed_role_handling(client, access_users):
    users = access_users
    async def create(person):
        response = await client.post('/api/v1/answer-workbench/tickets', headers={**person.headers, 'Idempotency-Key': str(uuid4())},
                                    json={'question': '请老师帮助安排复习'})
        assert response.status_code == 200, response.text
        return response.json()
    own = await create(users.student); outside = await create(users.outside)
    root = '/api/v1/answer-workbench/tickets/'
    read = await client.get(root+outside['id']+'?management=true', headers=users.mixed.headers)
    assert read.status_code == 200 and not read.json()['canClaim'] and not read.json()['canReply']
    read = await client.get(root+own['id']+'?management=true', headers=users.viewer.headers)
    assert read.status_code == 200 and not read.json()['canClaim']
    response = await client.post(root+own['id']+'/claim', headers={**users.viewer.headers, 'Idempotency-Key': str(uuid4())}, json={'expected': 1})
    assert response.status_code == 403
    response = await client.post(root+outside['id']+'/claim', headers={**users.mixed.headers, 'Idempotency-Key': str(uuid4())}, json={'expected': 1})
    assert response.status_code == 404
    claimed = await client.post(root+own['id']+'/claim', headers={**users.mixed.headers, 'Idempotency-Key': str(uuid4())}, json={'expected': 1})
    assert claimed.status_code == 200 and claimed.json()['canReply'], claimed.text
    response = await client.post(root+own['id']+'/reply', headers={**users.mixed.headers, 'Idempotency-Key': str(uuid4())},
        json={'expected': claimed.json()['revision'], 'text': '已收到，我会跟进学习安排。', 'reply_kind': 'routing', 'reviewed': True})
    assert response.status_code == 200 and response.json()['status'] == '已回复', response.text
