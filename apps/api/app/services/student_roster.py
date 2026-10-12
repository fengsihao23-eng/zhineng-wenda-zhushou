"""Student roster projection, school years, exports and historical attribution."""
from datetime import datetime, timedelta, timezone
import re
from uuid import UUID, uuid4
from sqlalchemy import select, func
from app.core.errors import ApiError
from app.db.models import (School, Student, User, ImportedClass, StudentYearClass,
                           StudentExamPlacement, StudentWorkflowTask, RosterImport,
                           StudentExamScore, StudentSubjectScore, QuestionScore, DiagnosisReport, Exam)
from app.services.education_common import data, digest
from app.services.roster_excel import (STUDENT_COLUMNS, STUDENT_CHANGE_COLUMNS, STUDENT_LOCKED_FIELDS,
                                      STUDENT_PROMOTION_COLUMNS, GRADE_NAMES, workbook_bytes)

STATUS_LABELS = {"active": "正常", "departed": "离校", "suspended": "离校", "withdrawn": "离校",
                 "inactive": "离校", "graduated": "毕业"}
KINDS = {"archive": "档案变更", "promotion": "升级/换班", "status": "离校/毕业/恢复在读",
         "deletion": "误导入删除", "identity": "姓名/账号变更"}


def default_year():
    date = datetime.now(timezone(timedelta(hours=8)))
    start = date.year if date.month >= 8 else date.year - 1
    return f"{start}-{start + 1}"


def year_after(year):
    try:
        start, end = map(int, year.split("-"))
        assert end == start + 1 and 2000 <= start <= 2200
    except (ValueError, AssertionError):
        raise ApiError(422, "ACADEMIC_YEAR_INVALID", "学年格式应为连续两年，如 2026-2027。") from None
    return f"{end}-{end + 1}"


async def school(db, school_id, lock=False):
    query = select(School).where(School.id == school_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    result = await db.scalar(query)
    if result is None:
        raise ApiError(404, "SCHOOL_NOT_AVAILABLE", "学校不存在。")
    return result


def current_year(item):
    return item.current_academic_year or default_year()


def grade_rank(value):
    value = str(value or "").strip()
    if value in GRADE_NAMES.values():
        return next(number for number, label in GRADE_NAMES.items() if label == value)
    if len(value) <= 2 and value.isdecimal() and 1 <= int(value) <= 12:
        return int(value)
    if value in {"复读班", "高中复读班"}:
        return 12
    return None


def segment(value):
    rank = grade_rank(value)
    return None if rank is None else "小学" if rank <= 6 else "初中" if rank <= 9 else "高中"


def graduating(value):
    return grade_rank(value) in {6, 9, 12}


async def people(db, school_id, identifiers=None, lock=False):
    query = select(Student, User).outerjoin(User, (User.id == Student.user_id) & (User.school_id == Student.school_id)).where(Student.school_id == school_id)
    if identifiers is not None:
        query = query.where(Student.id.in_(identifiers))
    if lock:
        query = query.with_for_update(of=Student).execution_options(populate_existing=True)
    return (await db.execute(query.order_by(Student.created_at, Student.id))).all()


async def class_map(db, school_id):
    return {item.id: item for item in (await db.scalars(select(ImportedClass).where(ImportedClass.school_id == school_id))).all()}


def fields31(student, user, school_item, classes):
    saved = student.profile_fields or {}
    # Historical uploads used trailing spaces on two headers. Read those values
    # without altering their retained originals; new files use r79's exact headers.
    fields = {column: str(saved.get(column, saved.get(column + " ", "")) or "") for column in STUDENT_COLUMNS}
    fields["学校编号"] = str(saved.get("学校编号", school_item.code) or "")
    fields["学校名称"] = str(saved.get("学校名称", school_item.name) or "")
    fields["姓名"], fields["账号"] = student.name, user.username if user else ""
    fields["学号"] = student.student_no or fields["学号"]
    from app.services.roster_workbench import _student_record_key
    _, grade, number = _student_record_key(student, classes)
    fields["年级（1-12）"], fields["班级号"] = grade, number
    fields["状态"] = STATUS_LABELS.get(student.status, student.status)
    fields["学生ID"] = str(student.id)
    return fields


def person_view(student, user, school_item, classes):
    fields = fields31(student, user, school_item, classes)
    normalized_status = "active" if student.status == "active" else "graduated" if student.status == "graduated" else "departed"
    return {**data(student, "id", "name", "student_no", "user_id", "source_system", "created_at", "archived_at"),
            "status": normalized_status, "original_status": student.status, "status_label": fields["状态"],
            "username": user.username if user else "", "account_enabled": bool(user and user.status == "active"),
            "fields": fields, "grade": fields["年级（1-12）"], "class_number": fields["班级号"],
            "class_name": fields["年级（1-12）"] + fields["班级号"], "class_id": str(student.class_id) if student.class_id else None,
            "external_class_id": student.external_class_id}


def fingerprint(student, user, fields):
    archived = student.archived_at
    if archived is not None:
        archived = archived.replace(tzinfo=timezone.utc) if archived.tzinfo is None else archived.astimezone(timezone.utc)
    return digest([fields, str(student.class_id or ""), str(student.external_class_id or ""), student.status,
                   str(student.user_id or ""), user.status if user else None, user.password_version if user else None,
                   archived.isoformat() if archived else ""])


async def context(db, actor):
    item = await school(db, actor.school_id)
    counts = (await db.execute(select(Student.status, func.count()).where(Student.school_id == actor.school_id).group_by(Student.status))).all()
    return {"current_year": current_year(item), "next_year": year_after(current_year(item)),
            "columns": STUDENT_COLUMNS, "change_columns": STUDENT_CHANGE_COLUMNS,
            "locked_fields": STUDENT_LOCKED_FIELDS, "promotion_columns": STUDENT_PROMOTION_COLUMNS,
            "status_counts": dict(counts)}


async def listing(db, actor, search="", class_name="", status="", page=1, page_size=20):
    item = await school(db, actor.school_id)
    classes = await class_map(db, actor.school_id)
    rows = [person_view(s, u, item, classes) for s, u in await people(db, actor.school_id)]
    keyword, class_keyword = search.strip().casefold(), class_name.strip().casefold()
    def class_matches(row):
        rank = grade_rank(row["grade"])
        number = re.fullmatch(r"(\d+)(?:班)?", row["class_number"])
        code = f"{rank}.{number[1]}" if rank and number else ""
        return not class_keyword or class_keyword in f"{row['grade']} {row['class_number']} {row['class_name']} {row['external_class_id'] or ''} {code}".casefold()
    filtered = [row for row in reversed(rows) if
                (not keyword or keyword in f"{row['name']} {row['username']} {row['student_no'] or ''}".casefold()) and
                class_matches(row) and
                (not status or row["status"] == status)]
    return {"items": filtered[(page - 1) * page_size:page * page_size], "total": len(filtered), "page": page,
            "page_size": page_size, "current_year": current_year(item)}


async def detail(db, actor, identifier):
    rows = await people(db, actor.school_id, [identifier])
    if not rows:
        raise ApiError(404, "RESOURCE_NOT_AVAILABLE", "档案不存在或不在授权范围内。")
    item = await school(db, actor.school_id)
    result = person_view(*rows[0], item, await class_map(db, actor.school_id))
    years = (await db.scalars(select(StudentYearClass).where(StudentYearClass.school_id == actor.school_id,
                                                           StudentYearClass.student_id == identifier).order_by(StudentYearClass.academic_year))).all()
    result["year_records"] = [data(row, "academic_year", "grade", "class_number", "status") for row in years]
    return result


async def archive_template(db, actor, identifiers):
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise ApiError(422, "STUDENT_SELECTION_REQUIRED", "请选择待变更的正常学生，学生ID不可重复。")
    rows = await people(db, actor.school_id, identifiers)
    if len(rows) != len(identifiers) or any(s.status != "active" for s, _ in rows):
        raise ApiError(422, "ACTIVE_STUDENTS_REQUIRED", "待变更名单仅可包含本校学籍状态为正常的学生。")
    item, classes = await school(db, actor.school_id), await class_map(db, actor.school_id)
    return workbook_bytes(STUDENT_CHANGE_COLUMNS, [[fields31(s, u, item, classes)[column] for column in STUDENT_CHANGE_COLUMNS] for s, u in rows], locked_fields=STUDENT_LOCKED_FIELDS)


async def resolve_class(db, school_id, grade, number):
    from app.services.roster_workbench import resolve_student_class
    classes = await class_map(db, school_id)
    values = {"年级（1-12）": grade, "班级号": number}
    match = await resolve_student_class(db, school_id, values, list(classes.values()))
    if match is not None:
        if match.status != "active":
            raise ApiError(422, "CLASS_INACTIVE", "目标班级已停用，请先核对班级。")
        return match
    # Promotion maintains real class references; new-student intake still permits
    # unrecognised/blank class labels and does not create dictionary entries.
    external = "roster-" + digest([grade, number])[:24]
    match = await db.scalar(select(ImportedClass).where(ImportedClass.school_id == school_id, ImportedClass.external_class_id == external))
    if match is None:
        match = ImportedClass(id=uuid4(), school_id=school_id, name=grade + number, external_class_id=external, source_system="native", status="active")
        db.add(match)
        await db.flush()
    return match


async def year_record(db, student, academic_year, fields, status=None, classroom=None):
    record = await db.scalar(select(StudentYearClass).where(StudentYearClass.school_id == student.school_id,
                                                           StudentYearClass.student_id == student.id,
                                                           StudentYearClass.academic_year == academic_year))
    fresh = record is None
    if fresh:
        record = StudentYearClass(id=uuid4(), school_id=student.school_id, student_id=student.id, academic_year=academic_year)
        db.add(record)
    record.grade = fields["年级（1-12）"]
    record.class_number = fields["班级号"]
    if classroom is not None or fresh:
        record.class_id = classroom.id if classroom else student.class_id
    record.status = status or student.status
    await db.flush()
    return record


async def freeze_history(db, student, fields, fallback_year, exam_ids=None):
    identifiers = set()
    for model in (StudentExamScore, StudentSubjectScore, QuestionScore, DiagnosisReport):
        query = select(model.exam_id).where(model.school_id == student.school_id, model.student_id == student.id)
        if exam_ids is not None:
            query = query.where(model.exam_id.in_(exam_ids))
        identifiers.update((await db.scalars(query)).all())
    existing = set((await db.scalars(select(StudentExamPlacement.exam_id).where(StudentExamPlacement.school_id == student.school_id,
                                                                            StudentExamPlacement.student_id == student.id))).all())
    for exam in (await db.scalars(select(Exam).where(Exam.school_id == student.school_id, Exam.id.in_(identifiers - existing)))).all():
        if exam.academic_year:
            year = exam.academic_year
        elif exam.start_date:
            start = exam.start_date.year if exam.start_date.month >= 8 else exam.start_date.year - 1
            year = f"{start}-{start + 1}"
        else:
            year = fallback_year
        historic = await db.scalar(select(StudentYearClass).where(StudentYearClass.school_id == student.school_id,
                                                                 StudentYearClass.student_id == student.id, StudentYearClass.academic_year == year))
        db.add(StudentExamPlacement(school_id=student.school_id, student_id=student.id, exam_id=exam.id, academic_year=year,
                                    grade=historic.grade if historic else fields["年级（1-12）"],
                                    class_number=historic.class_number if historic else fields["班级号"],
                                    class_id=historic.class_id if historic else student.class_id,
                                    external_class_id=student.external_class_id))
    await db.flush()


def task_view(item, full=True):
    result = {**data(item, "id", "kind", "status", "revision", "filename", "operator_name", "created_at", "confirmed_at", "reviewed_at"),
              "kind_label": KINDS.get(item.kind, item.kind), "has_original": item.original_content is not None,
              "report": item.report, "request_payload": item.request_payload, "preparation": item.preparation,
              "reviews": item.reviews, "confirmation": item.confirmation}
    if full:
        result.update(rows=item.rows, snapshots=item.snapshots)
    return result


async def task_listing(db, actor, search="", kind="", page=1, page_size=20):
    query = select(StudentWorkflowTask).where(StudentWorkflowTask.school_id == actor.school_id)
    if kind:
        query = query.where(StudentWorkflowTask.kind == kind)
    rows = (await db.scalars(query.order_by(StudentWorkflowTask.created_at.desc(), StudentWorkflowTask.id))).all()
    if search.strip():
        keyword = search.strip().casefold()
        rows = [r for r in rows if keyword in f"{r.id} {r.filename or ''} {r.operator_name} {r.request_payload} {[(s.get('fields', {}).get('姓名'), s.get('fields', {}).get('账号'), s.get('id')) for s in r.snapshots]}".casefold()]
    return {"items": [task_view(r, False) for r in rows[(page - 1) * page_size:page * page_size]], "total": len(rows), "page": page, "page_size": page_size}
