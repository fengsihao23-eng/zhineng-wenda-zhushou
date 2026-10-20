"""Reconcile roster duties when their class/subject dictionaries become available."""
from sqlalchemy import select

from app.db.models import School, User, Subject, TeacherProfile, TeachingAssignment
from app.db.models.import_batch import ImportedClass
from app.services.education_common import now
from app.services.roster_excel import (teaching_pairs, class_matches, class_references,
                                      grade_codes, subject_leadership, parse_class_reference, normalized, duty_codes)


def desired_grants(fields, duties, classes, subjects):
    duties = set(duties) | set(duty_codes(fields))
    grants, unresolved = set(), []
    pairs = teaching_pairs(fields.get("任课年级班级", ""))
    homes = class_references(fields.get("班主任年级班级", "")) if "HOMEROOM_TEACHER" in duties else []
    leaders = subject_leadership(fields.get("教研组长负责年级科目", "")) if "SUBJECT_LEADER" in duties else set()
    grades = grade_codes(fields.get("年级长负责年级", "")) if "GRADE_LEADER" in duties else set()
    references = [(f"{subject}:{grade}.{number}", lambda c, s, sub=subject, g=grade, n=number:
                   class_matches(c, g, n) and normalized(s.name) == sub) for subject, grade, number in pairs]
    references += [(f"班主任:{grade}.{number}", lambda c, s, g=grade, n=number: class_matches(c, g, n)) for grade, number in homes]
    references += [(f"教研组长:{grade}.{name}", lambda c, s, g=grade, name=name:
                    normalized(s.name) == name and classroom_grade(c) == g) for grade, name in leaders]
    references += [(f"年级长:{grade}", lambda c, s, g=grade: classroom_grade(c) == g) for grade in grades]
    for field, parsed in [("任课年级班级", pairs), ("班主任年级班级", homes),
                          ("教研组长负责年级科目", leaders), ("年级长负责年级", grades)]:
        if normalized(fields.get(field)) and not parsed:
            unresolved.append(f"{field}:{fields[field]}")
    for label, matches in references:
        resolved = {(c.id, s.id) for c in classes for s in subjects if matches(c, s)}
        grants.update(resolved)
        if not resolved:
            unresolved.append(label)
    return grants, unresolved


def classroom_grade(classroom):
    reference = parse_class_reference(classroom.external_class_id) or parse_class_reference(classroom.name)
    return reference[0] if reference else None


async def dictionaries(db, school_id):
    classes = (await db.scalars(select(ImportedClass).where(ImportedClass.school_id == school_id, ImportedClass.status == "active"))).all()
    subjects = (await db.scalars(select(Subject).where(Subject.school_id == school_id))).all()
    return classes, subjects


async def add_missing(db, user, fields, duties, classes, subjects, preserve_history=False):
    desired, unresolved = desired_grants(fields, duties, classes, subjects)
    query = select(TeachingAssignment.class_id, TeachingAssignment.subject_id).where(
        TeachingAssignment.school_id == user.school_id, TeachingAssignment.teacher_user_id == user.id)
    if not preserve_history:
        query = query.where(TeachingAssignment.status == "active")
    # A later dictionary update must never reopen a deliberately ended/expired grant.
    existing = set((await db.execute(query)).all())
    for class_id, subject_id in desired - existing:
        db.add(TeachingAssignment(school_id=user.school_id, teacher_user_id=user.id,
            class_id=class_id, subject_id=subject_id, starts_at=now(), status="active"))
    return len(desired - existing), unresolved


async def reconcile_school(db, school_id):
    await db.flush()
    # Serialize dictionary-triggered repairs, including concurrent exam saves.
    await db.scalar(select(School.id).where(School.id == school_id).with_for_update())
    classes, subjects = await dictionaries(db, school_id)
    rows = (await db.execute(select(User, TeacherProfile).join(TeacherProfile, TeacherProfile.id == User.id).where(
        User.school_id == school_id, TeacherProfile.school_id == school_id, User.status == "active"))).all()
    created, pending = 0, []
    for user, profile in rows:
        count, unresolved = await add_missing(db, user, profile.fields or {}, profile.duties or [], classes, subjects, preserve_history=True)
        created += count
        if unresolved:
            pending.append({"teacher_id": str(user.id), "references": unresolved})
    await db.flush()
    return {"created": created, "pending": pending}
