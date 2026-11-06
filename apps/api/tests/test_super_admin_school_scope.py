"""Platform governance and school business are separate authorization domains."""
from uuid import uuid4
import pytest
import pytest_asyncio
from sqlalchemy import select
from app.core.security import create_access_token
from app.db.models import School, User, Role, UserRole, Student, Exam
from app.db.models.exam_management import ExamAdministration


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
async def test_super_admin_has_governance_access_but_cannot_read_or_write_school_data(client, test_db, scoped_schools, sample_school_id):
    setup = scoped_schools
    owner = setup['owner']
    school_role = await test_db.scalar(select(Role).where(Role.code == 'SCHOOL_ADMIN'))
    # Stale mixed assignments must not re-enable school access for a super admin.
    test_db.add(UserRole(user_id=owner.id, school_id=owner.school_id, role_id=school_role.id))
    await test_db.commit()
    paths=['/platform/education/roster/teachers/records', '/platform/education/roster/students/records',
           '/platform/education/exam-management', '/platform/education/report-management',
           '/platform/management/schools', '/platform/management/students', '/platform/management/overview',
           '/answer-workbench/admin/state', '/admin/prompts/', '/admin/traces/audit']
    for headers in (setup['owner_headers'], setup['selected']):
        for path in paths:
            result = await client.get('/api/v1' + path, headers=headers)
            assert result.status_code == 403, (path, result.text)
            assert result.json()['error']['code'] == 'PLATFORM_ADMIN_GOVERNANCE_ONLY'
        result = await client.post('/api/v1/platform/education/school/subjects', headers=headers,
            json={'code': 'BLOCKED', 'name': '禁止修改', 'external_subject_id': 'BLOCKED'})
        assert result.status_code == 403 and result.json()['error']['code'] == 'PLATFORM_ADMIN_GOVERNANCE_ONLY'
    for path in ('', '/history', '/schools'):
        response = await client.get('/api/v1/platform/administrators' + path, headers=setup['owner_headers'])
        assert response.status_code == 200, response.text
    identity=await client.get('/api/v1/auth/me', headers=setup['owner_headers'])
    assert identity.json()['school_id']==str(sample_school_id)


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
async def test_school_admin_can_access_own_business_but_not_governance_or_foreign_exam(client, scoped_schools):
    setup = scoped_schools
    headers = setup['local_headers']
    for path in ('/platform/education/roster/teachers/records', '/platform/education/roster/students/records',
                 '/platform/education/exam-management', '/platform/education/report-management', '/answer-workbench/admin/state'):
        response = await client.get('/api/v1' + path, headers=headers)
        assert response.status_code == 200, (path, response.text)
    response = await client.get('/api/v1/platform/education/exam-management/' + str(setup['exam'].id), headers=headers)
    assert response.status_code == 404
    response = await client.get('/api/v1/platform/administrators', headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_large_school_prompt_catalog_uses_bounded_queries_and_preserves_identity(test_db, test_engine, scoped_schools):
    from sqlalchemy import event
    from app.api.deps import AuthenticatedUser
    from app.services.answer_workbench import catalog, person, permitted_exam_metadata
    setup=scoped_schools
    role=Role(id=uuid4(),code='STUDENT',name='Student')
    test_db.add(role);await test_db.flush()
    users=[]
    for index in range(35):
        user=User(id=uuid4(),school_id=setup['other'].id,username=f'catalog-{index}',display_name=f'Student {index}',password_hash='unused')
        test_db.add(user);await test_db.flush()
        test_db.add_all([UserRole(user_id=user.id,school_id=user.school_id,role_id=role.id),
            Student(id=uuid4(),school_id=user.school_id,user_id=user.id,name=user.display_name,status='active',profile_fields={'年级':'高中一年级'})])
        users.append(user)
    await test_db.commit()
    actor=AuthenticatedUser(setup['teacher'].id,setup['other'].id,setup['teacher'].username,['SCHOOL_ADMIN'])
    queries=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith('SELECT'):queries.append(statement)
    event.listen(test_engine.sync_engine,'before_cursor_execute',capture)
    try:result=await catalog(test_db,actor)
    finally:event.remove(test_engine.sync_engine,'before_cursor_execute',capture)
    assert len(result)==36 and len(queries)<=12
    expected=await person(test_db,actor,users[0].id,True)
    expected['scope']=await permitted_exam_metadata(test_db,actor,expected)
    assert next(row for row in result if row['userId']==str(users[0].id))==expected
    assert all(row['school']=='第二测试学校' for row in result)
