"""Super-admin selection is explicit; ordinary school identities cannot override it."""
from uuid import uuid4
import pytest
import pytest_asyncio
from sqlalchemy import select
from app.core.security import create_access_token
from app.db.models import School, User, Role, UserRole, Student, Exam
from app.db.models.exam_management import ExamAdministration
from app.db.models.answer_workbench import AnswerOperation
from app.db.models.trace import AuditLog


@pytest_asyncio.fixture
async def scoped_schools(test_db, sample_school_id):
    other = School(id=uuid4(), name='第二测试学校', code='SECOND-TEST', status='active')
    test_db.add(other)
    roles = {code: Role(id=uuid4(), code=code, name=code) for code in ('SUPER_ADMIN', 'SCHOOL_ADMIN', 'TEACHER')}
    test_db.add_all(roles.values())
    owner = User(id=uuid4(), school_id=sample_school_id, username='scope-owner', password_hash='not-used', status='active')
    ordinary = User(id=uuid4(), school_id=sample_school_id, username='scope-local', password_hash='not-used', status='active')
    teacher = User(id=uuid4(), school_id=other.id, username='scope-teacher', display_name='第二校教师', password_hash='not-used', status='active')
    test_db.add_all([owner, ordinary, teacher]); await test_db.flush()
    for user, code in [(owner, 'SUPER_ADMIN'), (ordinary, 'SCHOOL_ADMIN'), (teacher, 'TEACHER')]:
        test_db.add(UserRole(user_id=user.id, school_id=user.school_id, role_id=roles[code].id))
    student = Student(id=uuid4(), school_id=other.id, name='第二校学生', status='active')
    exam = Exam(id=uuid4(), school_id=other.id, name='第二校考试', external_exam_id='SECOND-EXAM', academic_year='2026-2027', exam_type='test')
    test_db.add_all([student, exam]); await test_db.flush()
    test_db.add(ExamAdministration(id=exam.id, school_id=other.id, configuration={
        'name': exam.name, 'academic_year': '2026-2027', 'exam_date': '2026-11-05', 'subjects': [], 'snapshots': {}, 'base_student_ids': []}))
    await test_db.commit()
    def headers(user):
        return {'Authorization': 'Bearer '+create_access_token({'sub': str(user.id), 'school_id': str(user.school_id)})}
    return {'owner': owner, 'ordinary': ordinary, 'teacher': teacher, 'other': other, 'student': student, 'exam': exam,
            'owner_headers': headers(owner), 'local_headers': headers(ordinary),
            'selected': {**headers(owner), 'X-School-ID': str(other.id)}}


@pytest.mark.asyncio
async def test_selected_school_rosters_exams_reports_and_global_management(client, test_db, scoped_schools, sample_school_id):
    setup=scoped_schools; headers=setup['selected']
    paths=['/platform/education/roster/teachers/records', '/platform/education/roster/students/records',
           '/platform/education/exam-management', '/platform/education/report-management']
    for path in paths:
        result=await client.get('/api/v1'+path, headers=headers)
        assert result.status_code==200, result.text
        body=result.json()
        assert body['school_id']==str(setup['other'].id) and body['school_name']=='第二测试学校' and body['school_code']=='SECOND-TEST'
        assert all(row['school_id']==str(setup['other'].id) for row in body['items'])
        if 'report-management' not in path: assert len(body['items'])==1
    schools=await client.get('/api/v1/platform/management/schools', headers=headers)
    assert [row['id'] for row in schools.json()]==[str(setup['other'].id)]
    students=await client.get('/api/v1/platform/management/students', headers=headers)
    assert [row['id'] for row in students.json()]==[str(setup['student'].id)]
    own_school=await client.get('/api/v1/platform/management/schools/'+str(sample_school_id), headers=headers)
    assert own_school.status_code==404
    identity=await client.get('/api/v1/auth/me', headers=setup['owner_headers'])
    assert identity.json()['school_id']==str(sample_school_id)
    await test_db.refresh(setup['owner']); assert setup['owner'].school_id==sample_school_id


@pytest.mark.asyncio
async def test_school_override_is_not_available_to_ordinary_users(client, scoped_schools):
    setup=scoped_schools
    for path in ['/platform/education/roster/students/records', '/platform/management/overview', '/answer-workbench/admin/state']:
        result=await client.get('/api/v1'+path, headers={**setup['local_headers'], 'X-School-ID': str(setup['other'].id)})
        assert result.status_code==403 and result.json()['error']['code']=='SCHOOL_SCOPE_FORBIDDEN'
    unchanged=await client.get('/api/v1/platform/education/roster/students/records', headers=setup['local_headers'])
    assert unchanged.status_code==200
    assert all(row['school_id']!=str(setup['other'].id) for row in unchanged.json()['items'])


@pytest.mark.asyncio
async def test_invalid_selection_never_falls_back_and_wrong_school_resource_is_denied(client, scoped_schools, sample_school_id):
    setup=scoped_schools
    for value,status in [('invalid',422),(str(uuid4()),404)]:
        response=await client.get('/api/v1/platform/education/roster/students/records',headers={**setup['owner_headers'],'X-School-ID':value})
        assert response.status_code==status
    for path in ['/auth/me','/platform/administrators']:
        assert (await client.get('/api/v1'+path,headers=setup['selected'])).status_code==400
    response=await client.get('/api/v1/platform/education/exam-management/'+str(setup['exam'].id), headers={**setup['owner_headers'],'X-School-ID':str(sample_school_id)})
    assert response.status_code==404


@pytest.mark.asyncio
async def test_cross_school_prompt_write_keeps_true_operator_and_target_school(client, test_db, scoped_schools, sample_school_id):
    setup=scoped_schools
    response=await client.get('/api/v1/answer-workbench/admin/state',headers=setup['selected'])
    assert response.status_code==200, response.text
    body=response.json(); assert body['operator']['school']=='第二测试学校' and body['operator']['schoolCode']=='SECOND-TEST'
    assert body['operator']['showSchoolColumn']
    stage=next(iter(body['stages']))
    response=await client.post('/api/v1/answer-workbench/admin/scopes/prompt:'+stage+'/draft',headers=setup['selected'],json={
        'expected':body['stages'][stage]['etag'],'draft':{'content':'第二校回答要求','format':'清楚回答','reason':'合成校验'}})
    assert response.status_code==200, response.text
    operation=await test_db.scalar(select(AnswerOperation).where(AnswerOperation.school_id==setup['other'].id))
    assert operation and operation.user_id==setup['owner'].id
    await test_db.refresh(setup['owner']); assert setup['owner'].school_id==sample_school_id
    logs=(await test_db.scalars(select(AuditLog).where(AuditLog.actor_id==setup['owner'].id,AuditLog.action=='administrator.request'))).all()
    assert any(row.extra_data['school_id']==str(setup['other'].id) for row in logs)


@pytest.mark.asyncio
async def test_disabled_school_is_read_only(client, test_db, scoped_schools):
    setup=scoped_schools; setup['other'].status='disabled'; await test_db.commit()
    assert (await client.get('/api/v1/platform/education/roster/students/records', headers=setup['selected'])).status_code==200
    response=await client.post('/api/v1/platform/education/school/subjects',headers=setup['selected'],json={'code':'X','name':'科目','external_subject_id':'X'})
    assert response.status_code==403 and response.json()['error']['code']=='SCHOOL_INACTIVE'
