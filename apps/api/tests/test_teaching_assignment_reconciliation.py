from datetime import datetime, timezone, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, func

from app.db.models import TeachingAssignment, Student
from app.services.teaching_assignments import reconcile_school
from app.services.roster_excel import teaching_pairs, class_references
from test_education_workbench import actors, post, P  # noqa: F401
from test_exam_management import exam_people, create  # noqa: F401
from test_roster_workflows import upload, confirm, teacher, classroom


@pytest.mark.asyncio
@pytest.mark.parametrize('exam_first', [True, False])
async def test_teacher_import_before_exam_and_classes_reconciles_in_either_order(client, test_db, actors, exam_people, exam_first):
    # Exercise the production session's disabled autoflush, rather than relying on fixture defaults.
    test_db.autoflush = False
    batch = await upload(client, [teacher('13800000181', 任课年级班级='数学：１０．１\n语文:高中一年级1班'),
                                  teacher('13800000182', name='合成班主任', 班主任年级班级='高中一年级1班')])
    done = await confirm(client, batch)
    ids = [UUID(row['id']) for row in done['report']['imported']]
    assert len(done['report']['unresolved_teaching']) == 2
    assert await test_db.scalar(select(func.count()).select_from(TeachingAssignment)) == 0
    if exam_first:
        await create(client, exam_people)
        room = await classroom(client)
    else:
        room = await classroom(client)
        await create(client, exam_people)
    rows = (await test_db.scalars(select(TeachingAssignment))).all()
    assert len(rows) == 4 and {row.teacher_user_id for row in rows} == set(ids)
    assert (await reconcile_school(test_db, actors['school'].id))['created'] == 0
    # A valid student class assignment exposes that student's roster to the imported teacher.
    student = await test_db.get(Student, actors['student'].id)
    student.class_id = UUID(room['id'])
    await test_db.commit()
    from app.api.deps import AuthenticatedUser
    from app.core.access_scope import student_ids
    actor = AuthenticatedUser(ids[0], actors['school'].id, 'synthetic', ['TEACHER'])
    assert actors['student'].id in (await test_db.scalars(student_ids(actor))).all()
    # Dictionary reconciliation must retain ended grants and not renew expired active grants.
    rows[0].status = 'ended'
    rows[1].expires_at = datetime.now(timezone.utc)-timedelta(days=1)
    await test_db.commit()
    assert (await reconcile_school(test_db, actors['school'].id))['created'] == 0
    await test_db.commit()
    assert await test_db.scalar(select(func.count()).select_from(TeachingAssignment)) == 4
    assert rows[0].status == 'ended' and rows[1].expires_at is not None


def test_normalized_roster_references_keep_subject_class_pairs():
    assert teaching_pairs('数学：１０．０１，１０．２；\n语文:高中二年级3班') == [('数学', 10, 1), ('数学', 10, 2), ('语文', 11, 3)]
    assert class_references('高中一年级26班\n１１．０１') == [(10, 26), (11, 1)]
    assert not teaching_pairs('数学:不确定班级')


@pytest.mark.asyncio
async def test_teacher_then_exam_then_promotion_binds_new_class_and_exposes_students(client, test_db, actors, exam_people):
    from app.api.deps import AuthenticatedUser, get_current_user
    from app.main import app
    from app.db.models import ExamQueryGrant
    from test_student_r79 import task_create, task_prepare, task_confirm, existing_fields
    batch = await confirm(client, await upload(client, [teacher('13800000183', 任课年级班级='数学：10.26', 班主任年级班级='高中一年级26班')]))
    teacher_id = UUID(batch['report']['imported'][0]['id'])
    await create(client, exam_people, subjects=1)
    assert await test_db.scalar(select(func.count()).select_from(TeachingAssignment)) == 0
    fields = await existing_fields(client, actors['student'].id)
    task = await task_create(client, 'promotion', values=[{'学生ID': fields['学生ID'], '账号': fields['账号'],
        '姓名': fields['姓名'], '目标年级': '高中一年级', '目标班级号': '26班'}], mode='current')
    done = await task_confirm(client, await task_prepare(client, task))
    assert done['status'] == 'succeeded'
    assert await test_db.scalar(select(func.count()).select_from(TeachingAssignment)) == 1
    assert await test_db.scalar(select(func.count()).select_from(ExamQueryGrant)) == 0
    actor = AuthenticatedUser(teacher_id, actors['school'].id, 'synthetic-teacher', ['TEACHER', 'HOMEROOM_TEACHER'])
    app.dependency_overrides[get_current_user] = lambda: actor
    students = await client.get('/api/v1/platform/management/students')
    assert students.status_code == 200 and [row['id'] for row in students.json()] == [str(actors['student'].id)]
