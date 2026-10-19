"""Synthetic accounts and year/class records for the isolated exam browser suite."""
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.db.models import (School, User, Role, UserRole, Student, StudentYearClass,
                           ImportedClass, Subject, TeachingAssignment, TeacherProfile)


async def main():
    password = sys.stdin.read().strip()
    if len(password) < 24:
        raise RuntimeError("An ephemeral synthetic credential is required")
    async with AsyncSessionLocal() as db:
        school = School(id=uuid4(), code="EXAM-QA-"+uuid4().hex[:12], name="考务验收学校", current_academic_year="2026-2027")
        db.add(school); await db.flush()
        roles = {}
        for code in ["SCHOOL_ADMIN", "TEACHER", "STUDENT", "SCHOOL_VIEWER", "EXAM_ADMIN", "SUBJECT_LEADER", "ACADEMIC_DIRECTOR"]:
            role = await db.scalar(select(Role).where(Role.code == code))
            if not role:
                role = Role(id=uuid4(), code=code, name=code); db.add(role); await db.flush()
            roles[code] = role.id
        users, students = {}, []
        for key, role in [("admin","SCHOOL_ADMIN"), ("teacher","TEACHER"), ("teacher2","TEACHER"), ("teacherexam","TEACHER"),
                          ("teacherleader","TEACHER"), ("teachermixed","TEACHER"), ("teacherschool","TEACHER"), ("teacheroutside","TEACHER"),
                          ("viewer","SCHOOL_VIEWER"), ("examadmin","EXAM_ADMIN"),
                          ("student","STUDENT"), ("student2","STUDENT"), ("student3","STUDENT"), ("inactive","STUDENT")]:
            user = User(id=uuid4(), school_id=school.id, username="exam-"+key+"-"+uuid4().hex[:8],
                        display_name={"admin":"考务验收管理员", "teacher":"数学教师甲", "teacher2":"语文教师乙"}.get(key, "考务验收"+key),
                        password_hash=get_password_hash(password))
            db.add(user); await db.flush()
            db.add(UserRole(school_id=school.id, user_id=user.id, role_id=roles[role])); users[key] = user
        db.add(UserRole(school_id=school.id, user_id=users["teacherexam"].id, role_id=roles["EXAM_ADMIN"]))
        classes = []
        for index in [1,2]:
            c = ImportedClass(id=uuid4(), school_id=school.id, external_class_id=f"10.{index}", name=f"高中一年级{index}班", source_system="native")
            db.add(c); classes.append(c)
        subjects = []
        for code,name in [("MATH","数学"),("CHINESE","语文"),("ENGLISH","英语")]:
            subject = Subject(id=uuid4(), school_id=school.id, code=code, name=name, source_system="native")
            db.add(subject); subjects.append(subject)
        await db.flush()
        for index,key in enumerate(["student","student2","student3","inactive"]):
            classroom = classes[0] if index < 2 else classes[1]
            student = Student(id=uuid4(), school_id=school.id, user_id=users[key].id,
                name="合成同名学生" if index < 2 else "合成学生丙" if index == 2 else "合成已毕业学生",
                status="graduated" if key == "inactive" else "active", class_id=classroom.id,
                external_class_id=classroom.external_class_id,
                profile_fields={"年级（1-12）":"高中一年级", "班级号":str(1 if index < 2 else 2), "状态":"毕业" if key == "inactive" else "正常"})
            db.add(student); await db.flush()
            db.add(StudentYearClass(school_id=school.id, student_id=student.id, academic_year="2026-2027",
                grade="高中一年级", class_number=str(1 if index < 2 else 2), class_id=classroom.id,
                status="graduated" if key == "inactive" else "active"))
            if index < 2:
                db.add(StudentYearClass(school_id=school.id, student_id=student.id, academic_year="2025-2026",
                    grade="初中三年级", class_number="8", class_id=classroom.id))
            students.append(student)
        for key,index in [("teacher",0),("teacher2",1)]:
            db.add(TeachingAssignment(school_id=school.id, teacher_user_id=users[key].id, class_id=classes[index].id,
                subject_id=subjects[index].id, starts_at=datetime.now(timezone.utc)-timedelta(days=1)))
            db.add(TeacherProfile(id=users[key].id, school_id=school.id,
                fields={"教师姓名":users[key].display_name,"任课年级班级":f"{subjects[index].name}:10.{index+1}",
                        "班主任年级班级":"10.1" if key == "teacher2" else ""},
                duties=["TEACHER", "HOMEROOM_TEACHER"] if key == "teacher2" else ["TEACHER"]))
        for key, fields, duties in [
            ("teacherleader", {"任课年级班级":"英语:10.22", "教研组长负责年级科目":"10.英语"}, ["TEACHER","SUBJECT_LEADER"]),
            ("teachermixed", {"任课年级班级":"数学:10.1;语文:10.2"}, ["TEACHER"]),
            ("teacheroutside", {"任课年级班级":"物理：１１.０１；化学：１２.２"}, ["TEACHER"]),
            ("teacherschool", {"任课年级班级":"英语:10.22", "是否教务主任":"是"}, ["TEACHER","ACADEMIC_DIRECTOR"]),
        ]:
            db.add(TeacherProfile(id=users[key].id, school_id=school.id, fields=fields, duties=duties))
            for duty in duties:
                if duty != "TEACHER":
                    db.add(UserRole(school_id=school.id, user_id=users[key].id, role_id=roles[duty]))
        await db.commit()
        print(json.dumps({"users":{key:user.username for key,user in users.items()}, "user_ids":{key:str(user.id) for key,user in users.items()},
            "school_id":str(school.id), "students":[{"id":str(s.id),"platform_id":str(s.platform_id),"name":s.name} for s in students]}, ensure_ascii=False))


asyncio.run(main())
