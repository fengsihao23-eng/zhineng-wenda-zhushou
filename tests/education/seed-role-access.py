"""Additional synthetic identities for the isolated role-access browser suite."""
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4
from sqlalchemy import select, update
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.core.security import get_password_hash
from app.db.models import User, Role, UserRole, Student, StudentYearClass, ImportedClass, Subject, TeachingAssignment, TeacherProfile


async def main():
    if settings.APP_ENV != 'test' or 'exam_v17_browser' not in str(settings.DATABASE_URL):
        raise RuntimeError('This seed requires an explicitly disposable test database')
    target = Path(sys.argv[1]); fixture = json.loads(target.read_text())
    async with AsyncSessionLocal() as db:
        if len(sys.argv) > 2 and sys.argv[2] == 'force-password':
            await db.execute(update(User).where(User.id == UUID(fixture['user_ids']['access_runtime'])).values(must_change_password=True))
            await db.commit()
        else:
            password = sys.stdin.read().strip()
            if len(password) < 24:
                raise RuntimeError('An ephemeral credential is required')
            school = UUID(fixture['school_id'])
            roles = {role.code: role for role in (await db.scalars(select(Role))).all()}
            for code in ['SUPER_ADMIN', 'PRINCIPAL']:
                if code not in roles:
                    role = Role(id=uuid4(), code=code, name=code); db.add(role); roles[code] = role
            await db.flush()
            classrooms = {c.external_class_id: c for c in (await db.scalars(select(ImportedClass).where(ImportedClass.school_id == school))).all()}
            subject = await db.scalar(select(Subject).where(Subject.school_id == school, Subject.code == 'MATH'))
            hashed = get_password_hash(password)
            fixture['role_access'] = {'class_id': str(classrooms['10.1'].id), 'other_class_id': str(classrooms['10.2'].id), 'subject_id': str(subject.id), 'students': {}}
            accounts = [('viewer', ['SCHOOL_VIEWER']), ('teacher', ['TEACHER']), ('exam', ['TEACHER', 'EXAM_ADMIN']),
                        ('principal', ['TEACHER', 'PRINCIPAL', 'SCHOOL_VIEWER']), ('super', ['SUPER_ADMIN']),
                        ('runtime', ['STUDENT']), ('initial', ['STUDENT']), ('outside', ['STUDENT'])]
            for key, codes in accounts:
                alias = 'access_'+key
                user = User(id=uuid4(), school_id=school, username=alias+'-'+uuid4().hex[:8], display_name='角色回归 '+key,
                            account_type='student' if 'STUDENT' in codes else 'teacher' if 'TEACHER' in codes else 'general',
                            password_hash=hashed, must_change_password=key == 'initial')
                db.add(user); await db.flush()
                for code in codes:
                    db.add(UserRole(school_id=school, user_id=user.id, role_id=roles[code].id))
                fixture['users'][alias] = user.username; fixture['user_ids'][alias] = str(user.id)
                if 'TEACHER' in codes:
                    fields = {'教师姓名': user.display_name, '任课年级班级': '数学:10.1'}
                    if key == 'principal':
                        fields['是否校长'] = '是'
                    db.add(TeacherProfile(id=user.id, school_id=school, fields=fields, duties=['TEACHER', 'PRINCIPAL'] if key == 'principal' else ['TEACHER']))
                    db.add(TeachingAssignment(school_id=school, teacher_user_id=user.id, class_id=classrooms['10.1'].id,
                                             subject_id=subject.id, starts_at=datetime.now(timezone.utc)-timedelta(days=1)))
                if 'STUDENT' in codes:
                    classroom = classrooms['10.2' if key == 'outside' else '10.1']
                    student = Student(id=uuid4(), school_id=school, user_id=user.id, name='角色回归学生 '+key,
                                      status='active', class_id=classroom.id, profile_fields={'年级': '高中一年级'})
                    db.add(student); await db.flush()
                    db.add(StudentYearClass(school_id=school, student_id=student.id, academic_year='2026-2027',
                                           grade='高中一年级', class_number='2' if key == 'outside' else '1', class_id=classroom.id, status='active'))
                    fixture['role_access']['students'][key] = str(student.id)
            await db.commit()
            target.write_text(json.dumps(fixture, ensure_ascii=False))
    await engine.dispose()


asyncio.run(main())
