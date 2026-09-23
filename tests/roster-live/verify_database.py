"""Independent aggregate readback after real-data and real-provider acceptance."""
import asyncio
import json
import re
import os
from pathlib import Path
from uuid import UUID
from sqlalchemy import select, func
os.environ["DEBUG"] = "false"
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.db.models import User, Role, UserRole, Student, ImportedClass, Subject, TeachingAssignment, StudentExamScore, StudentSubjectScore, QuestionScore, ChatSession, ChatMessage, ModelUsageLog, AuditLog
from app.db.models.roster import TeacherProfile, RosterImport, ParentBinding

ROOT=Path(__file__).resolve().parents[2]
PRIVATE=ROOT/'.local/yjyz-roster'


async def main():
    if settings.DATABASE_URL != 'postgresql+asyncpg://qa_education@127.0.0.1:55449/yjyz_roster_20260922':
        raise RuntimeError('Dedicated database required')
    fixture=json.loads((PRIVATE/'acceptance-fixture.json').read_text())
    report=json.loads((PRIVATE/'acceptance-report.json').read_text())
    school_id=UUID(fixture['identity']['school_id'])
    async with AsyncSessionLocal() as db:
        profiles=(await db.scalars(select(TeacherProfile).where(TeacherProfile.school_id==school_id))).all()
        users={u.id:u for u in (await db.scalars(select(User).where(User.school_id==school_id))).all()}
        roles=(await db.execute(select(Role.code,func.count()).join(UserRole,UserRole.role_id==Role.id).where(UserRole.school_id==school_id,UserRole.user_id.in_([p.id for p in profiles])).group_by(Role.code))).all()
        assert len(profiles)==160
        for profile in profiles:
            user=users[profile.id]
            assert user.status=='active' and user.must_change_password and user.password_version==0
        role_counts=dict(roles)
        assert role_counts=={'TEACHER':160,'HOMEROOM_TEACHER':32,'SUBJECT_LEADER':5,'GRADE_LEADER':2,'SCHOOL_ADMIN':1,'EXAM_ADMIN':2}
        classes={c.id:c for c in (await db.scalars(select(ImportedClass).where(ImportedClass.school_id==school_id))).all()}
        subjects={s.id:s for s in (await db.scalars(select(Subject).where(Subject.school_id==school_id))).all()}
        assignments=(await db.scalars(select(TeachingAssignment).where(TeachingAssignment.school_id==school_id))).all()
        multi=next(p for p in profiles if p.fields.get('教研组长负责年级科目')=='10.语文,10.英语')
        multi_grants=[a for a in assignments if a.teacher_user_id==multi.id]
        assert len(multi_grants)==64
        assert {subjects[a.subject_id].name for a in multi_grants}=={'语文','英语'}
        assert len({a.class_id for a in multi_grants})==32
        # Independently reconstruct every direct teaching reference from raw workbook cells.
        direct_count=0
        for profile in profiles:
            for subject_name,codes in re.findall(r'([^:;]+):([^;]+)',profile.fields.get('任课年级班级','')):
                for code in codes.split(','):
                    code=code.strip()
                    assert any(a.teacher_user_id==profile.id and subjects[a.subject_id].name==subject_name.strip() and classes[a.class_id].external_class_id==code for a in assignments)
                    direct_count+=1
        batch=await db.get(RosterImport,UUID(report['import_batch_id']))
        assert batch.report['success_count']==160 and not batch.report['unresolved_teaching']
        audit_count=await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='education.roster.import',AuditLog.resource_id==batch.id))
        assert audit_count==1
        student_id=UUID(report['graduated_student_id']); student=await db.get(Student,student_id)
        assert student.status=='graduated' and (await db.get(User,student.user_id)).status=='graduated'
        counts={}
        for model in (StudentExamScore,StudentSubjectScore,QuestionScore,ChatSession):
            counts[model.__tablename__]=await db.scalar(select(func.count()).select_from(model).where(model.student_id==student_id))
        assert all(value>0 for value in counts.values())
        messages=await db.scalar(select(func.count()).select_from(ChatMessage).join(ChatSession,ChatSession.id==ChatMessage.session_id).where(ChatSession.student_id==student_id))
        assert messages>=4
        binding=await db.scalar(select(ParentBinding).where(ParentBinding.student_id==student_id))
        assert binding.status=='revoked'
        usage=await db.scalar(select(ModelUsageLog).where(ModelUsageLog.agent_run_id==UUID(report['real_model_answer']['agent_run_id'])))
        assert usage.model=='deepseek-flash' and usage.provider=='DeepSeek' and usage.total_tokens>0
        report['database_readback']={'teacher_count':len(profiles),'classes':len(classes),'subjects':len(subjects),'direct_teaching_references':direct_count,'effective_grants':len(assignments),'roles':role_counts,'multi_subject_leader_grants':len(multi_grants),'import_audit_entries':audit_count,'real_staff_active_and_password_unchanged':160,'graduation_preserved_records':counts,'graduation_preserved_messages':messages,'parent_binding_status':binding.status,'model_usage':{'provider':usage.provider,'model':usage.model,'prompt_tokens':usage.prompt_tokens,'completion_tokens':usage.completion_tokens,'total_tokens':usage.total_tokens,'latency_ms':usage.latency_ms}}
        report['database_verified']=True
    (PRIVATE/'acceptance-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report['database_readback'],ensure_ascii=False))


if __name__=='__main__':asyncio.run(main())
