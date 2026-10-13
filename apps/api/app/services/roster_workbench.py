"""All-or-nothing roster import, explicit duplicate choices and guarded lifecycle."""
from uuid import UUID, uuid4
import asyncio
import base64
import re
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select, delete, or_, func
from app.core.errors import ApiError
from app.core.security import get_password_hash
from app.db.base import Base
from app.db.models.user import User, Role, UserRole
from app.db.models.student import Student
from app.db.models.roster import TeacherProfile, TeacherDeletion, RosterImport
from app.db.models.import_batch import ImportedClass
from app.db.models.teaching import TeachingAssignment
from app.db.models.exam import Subject
from app.services.education_common import audit, owned, claim, data, digest, now
from app.services.roster_excel import (
    COLUMNS, TEACHER_COLUMNS, TEACHER_CHANGE_COLUMNS, ERROR_COLUMNS, GRADE_NAMES, parse_excel, error_row,
    workbook_bytes, teaching_pairs, class_matches, duty_codes, subject_leadership,
)

ROLE_NAMES = {"TEACHER": "任课教师", "STUDENT": "学生", "HOMEROOM_TEACHER": "班主任", "SUBJECT_LEADER": "备课 / 教研组长", "GRADE_LEADER": "年级长", "ACADEMIC_DIRECTOR": "教务主任", "PRINCIPAL": "校长", "GENERAL_DIRECTOR": "总务主任", "SCHOOL_VIEWER": "全校基础数据查看", "SCHOOL_ADMIN": "学校管理员", "EXAM_ADMIN": "考试管理员"}


def role_users(school_id, role):
    return select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(UserRole.school_id == school_id, Role.code == role)


def _student_text(value):
    return "" if value is None else str(value).strip()


def _student_key(values):
    return (
        _student_text(values.get("姓名")),
        _student_text(values.get("年级（1-12）")),
        _student_text(values.get("班级号")),
    )


def _student_record_key(student, classes_by_id):
    fields = student.profile_fields or {}
    name = _student_text(student.name)
    grade = _student_text(fields.get("年级（1-12）"))
    class_number = _student_text(fields.get("班级号"))
    if grade and class_number:
        return name, grade, class_number

    classroom = classes_by_id.get(student.class_id)
    external_class_id = _student_text(student.external_class_id)
    if classroom is None and external_class_id:
        classroom = next(
            (item for item in classes_by_id.values() if _student_text(item.external_class_id) == external_class_id),
            None,
        )
    if classroom is not None:
        external_class_id = _student_text(classroom.external_class_id)
        compact_name = _student_text(classroom.name).replace(" ", "")
        for label in GRADE_NAMES.values():
            if compact_name.startswith(label):
                suffix = compact_name[len(label):]
                if suffix:
                    return name, label, suffix if suffix.endswith("班") else f"{suffix}班"
        match = re.fullmatch(r"(\d+)\.(\d+)", external_class_id)
        if match:
            return name, GRADE_NAMES.get(int(match[1]), ""), f"{match[2]}班"
    match = re.fullmatch(r"(\d+)\.(\d+)", external_class_id)
    if match:
        return name, GRADE_NAMES.get(int(match[1]), ""), f"{match[2]}班"
    return name, grade, class_number


async def resolve_student_class(db, school_id, values, classes=None):
    grade_name, number = values.get("年级（1-12）", "").strip(), values.get("班级号", "").strip()
    if not grade_name or not number:
        return None
    grade = next((g for g, label in GRADE_NAMES.items() if label == grade_name), None)
    match = re.fullmatch(r"(\d+)班", number)
    if classes is None:
        classes = (await db.scalars(select(ImportedClass).where(ImportedClass.school_id == school_id, ImportedClass.status == "active"))).all()
    matches = [c for c in classes if c.name.replace(" ", "") == f"{grade_name}{number}" or (grade is not None and match and class_matches(c, grade, int(match[1])))]
    return matches[0] if len(matches) == 1 else None


async def preflight(db, school_id, kind, rows):
    role = "TEACHER" if kind == "teachers" else "STUDENT"
    account_scope = or_(User.id.in_(role_users(school_id, role)), User.account_type == role.lower())
    if kind == "students":
        account_scope = or_(account_scope, User.id.in_(select(Student.user_id).where(Student.school_id == school_id, Student.user_id.is_not(None))))
    existing = (await db.scalars(select(User).where(User.school_id == school_id, User.status != "deleted", account_scope))).all()
    accounts = {u.username for u in existing}
    profiles = (await db.scalars(select(TeacherProfile).where(TeacherProfile.school_id == school_id))).all() if kind == "teachers" else []
    staff = {u.id: u for u in existing}
    classes = (await db.scalars(select(ImportedClass).where(ImportedClass.school_id == school_id))).all() if kind == "students" else []
    student_matches = {}
    if kind == "students":
        student_rows = (await db.execute(
            select(Student, User)
            .outerjoin(User, User.id == Student.user_id)
            .where(Student.school_id == school_id)
        )).all()
        classes_by_id = {item.id: item for item in classes}
        for existing_student, existing_user in student_rows:
            key = _student_record_key(existing_student, classes_by_id)
            if key[0]:
                student_matches.setdefault(key, []).append({
                    "id": str(existing_student.id),
                    "platform_id": str(existing_student.platform_id),
                    "name": existing_student.name,
                    "account": existing_user.username if existing_user else "",
                    "grade_class": f"{key[1]} · {key[2]}",
                })
    seen, issues, suspicious = {}, [], []
    file_student_matches = {}
    if kind == "students":
        for row in rows:
            key = _student_key(row["values"])
            if key[0]:
                file_student_matches.setdefault(key, []).append({"row_number": row["row_number"],
                    "name": row["values"]["姓名"].strip(), "account": row["values"]["账号"].strip(),
                    "grade_class": f"{key[1]} · {key[2]}", "source": "file"})
    name_field, account_field = ("教师姓名", "教师账号") if kind == "teachers" else ("姓名", "账号")
    for row in rows:
        values, number = row["values"], row["row_number"]
        name, account = values[name_field].strip(), values[account_field].strip()
        types, fields, messages, suggestions = [], [], [], []

        def issue(kind_, field, message, suggestion):
            types.append(kind_)
            fields.append(field)
            messages.append(message)
            suggestions.append(suggestion)

        for field in (name_field, account_field):
            if not values[field].strip():
                issue("必填缺失", field, f"必填项「{field}」为空", "逐项补填后整表重新上传")
            elif len(values[field].strip()) > 100:
                issue("字段过长", field, f"「{field}」超过账号系统的 100 字限制", "缩短该字段后整表重新上传")
        if account:
            duplicate_type = "教师账号重复" if role == "TEACHER" else "账号重复"
            if account in accounts:
                existing_message = "与系统已有同类账号重复" if role == "TEACHER" else "与系统已有学生账号重复（库内已存在，账号即登录账号）"
                issue(duplicate_type, account_field, existing_message, "如需变更，请在教师列表选择对应删除原因" if kind == "teachers" else "修正账号后整表重传；本人资料修改请走档案变更或姓名·账号变更")
            if account in seen:
                issue(duplicate_type, account_field, f"与本次文件内第 {seen[account]} 行账号重复", "同一账号只保留一行，修正后整表重新上传")
            seen.setdefault(account, number)
        if kind == "teachers":
            if account and not re.fullmatch(r"1[3-9]\d{9}", account):
                issue("格式错误", "教师账号", "教师账号须填写完整的 11 位手机号，作为登录账号", "补填完整手机号后整表重新上传")
            # Contact values may be masked in source exports. Only the teacher
            # account must be a complete mobile number; retain contact text as-is.
            if values["状态"] != "正常":
                issue("状态非法", "状态", "「状态」仅允许「正常」", "改回「正常」；离职 / 停用请在教师列表操作")
            teaching = values["任课年级班级"]
            matches = []
            if teaching.strip() and name:
                for profile in profiles:
                    user = staff.get(profile.id)
                    if user and values[name_field] == profile.fields.get("教师姓名", user.display_name or "") and teaching == profile.fields.get("任课年级班级", ""):
                        matches.append({"id": str(user.id), "platform_id": str(user.platform_id), "name": user.display_name, "account": user.username, "teaching": teaching, "subjects_grades": [teaching]})
                if matches:
                    grouped = {}
                    for match in matches:
                        previous = grouped.setdefault(match["id"], {**match, "subjects_grades": []})
                        previous["subjects_grades"] = sorted(set(previous["subjects_grades"] + match["subjects_grades"]))
                    matches = sorted(grouped.values(), key=lambda match: match["id"])
                    suspicious.append({"row_number": number, "name": name, "account": account, "teaching": teaching, "keep": True, "matches": matches})
        else:
            if values["状态"] != "正常":
                issue("状态非法", "状态", "「状态」仅允许「正常」", "改回「正常」；离校 / 毕业 / 恢复在读请在学生列表办理")
            # Grade and class are retained as student profile data only. The
            # new-student flow deliberately does not require a class dictionary
            # match; an optional match is resolved during the write step.
            key = _student_key(values)
            same_file = [match for match in file_student_matches.get(key, []) if match["row_number"] != number]
            matches = student_matches.get(key, []) + same_file
            if key[0] and matches:
                suspicious.append({
                    "row_number": number,
                    "name": name,
                    "account": account,
                    "keep": True,
                    "matches": matches,
                })
        if messages:
            issues.append(error_row(row, types, fields, messages, suggestions, kind))
    report = {"ok": not issues, "issues": issues, "suspicious": suspicious, "total_rows": len(rows)}
    return report


def view(item):
    return {**data(item, "id", "kind", "filename", "content_hash", "status", "revision", "report", "operator_name", "created_at", "confirmed_at", "change_task_id", "confirmation"), "has_original": item.original_content is not None, "columns": TEACHER_CHANGE_COLUMNS if item.change_task_id else COLUMNS[item.kind], "rows": item.rows}


async def upload(db, actor, kind, body, key):
    rows, issues = parse_excel(kind, body.filename, body.content_base64)
    identifier, fresh = await claim(db, actor, f"roster.upload.{kind}", key, body.model_dump())
    if fresh:
        report = {"ok": False, "issues": issues, "suspicious": [], "total_rows": 0} if issues else await preflight(db, actor.school_id, kind, rows)
        operator = await db.get(User, actor.user_id)
        item = RosterImport(id=identifier, school_id=actor.school_id, kind=kind, filename=body.filename, content_hash=digest(body.content_base64), original_content=base64.b64decode(body.content_base64), rows=rows, report=report, status="ready" if report["ok"] else "invalid", created_by=actor.user_id, operator_name=operator.display_name or operator.username)
        db.add(item)
        audit(db, actor, "roster.preflight", item, {"kind": kind, "error_rows": len(report["issues"])})
        await db.commit()
    return view(await owned(db, RosterImport, identifier, actor))


async def grant_roles(db, user, codes):
    for code in codes:
        role = await db.scalar(select(Role).where(Role.code == code))
        if role is None:
            role = Role(id=uuid4(), code=code, name=ROLE_NAMES.get(code, code))
            db.add(role)
            await db.flush()
        db.add(UserRole(user_id=user.id, school_id=user.school_id, role_id=role.id))


async def teacher_grants(db, user, values, duties):
    classes = (await db.scalars(select(ImportedClass).where(ImportedClass.school_id == user.school_id, ImportedClass.status == "active"))).all()
    subjects = (await db.scalars(select(Subject).where(Subject.school_id == user.school_id))).all()
    pairs = teaching_pairs(values["任课年级班级"])
    homeroom = values["班主任年级班级"].strip()
    leaders = subject_leadership(values["教研组长负责年级科目"])
    grade_leader = values["年级长负责年级"].strip()
    grants, unresolved = set(), []
    for subject, grade, number in pairs:
        matches = [(c, s) for c in classes for s in subjects if class_matches(c, grade, number) and s.name == subject]
        if not matches:
            unresolved.append(f"{subject}:{grade}.{number}")
        grants.update((c.id, s.id) for c, s in matches)
    for classroom in classes:
        for subject in subjects:
            match = re.fullmatch(r"(\d+)\.(\d+)", homeroom)
            is_home = "HOMEROOM_TEACHER" in duties and match and class_matches(classroom, int(match[1]), int(match[2]))
            is_subject = "SUBJECT_LEADER" in duties and any(subject.name == name and (classroom.external_class_id.startswith(f"{grade}.") or classroom.name.startswith(GRADE_NAMES.get(grade, "!"))) for grade, name in leaders)
            is_grade = "GRADE_LEADER" in duties and grade_leader.isdigit() and (classroom.external_class_id.startswith(grade_leader + ".") or classroom.name.startswith(GRADE_NAMES.get(int(grade_leader), "!")))
            if is_home or is_subject or is_grade:
                grants.add((classroom.id, subject.id))
    for class_id, subject_id in grants:
        db.add(TeachingAssignment(school_id=user.school_id, teacher_user_id=user.id, class_id=class_id, subject_id=subject_id, starts_at=now(), status="active"))
    return unresolved


async def student_password_hashes(rows):
    # A full grade can contain thousands of students; keep bcrypt's cost while
    # bounding CPU work instead of hashing each account serially on import.
    slots = asyncio.Semaphore(8)

    async def hash_row(row):
        async with slots:
            return row["row_number"], await run_in_threadpool(get_password_hash, row["values"]["账号"].strip())

    return dict(await asyncio.gather(*(hash_row(row) for row in rows)))


async def confirm(db, actor, identifier, body):
    item = await owned(db, RosterImport, identifier, actor, lock=True)
    if item.change_task_id:
        from app.services.teacher_changes import confirm_task_batch
        return await confirm_task_batch(db, actor, item, body)
    if body.teacher_replacements:
        raise ApiError(422, "TEACHER_TASK_REQUIRED", "资料变更须在绑定原教师ID的专属任务内导入；普通导入只新增教师。")
    payload = body.model_dump(mode="json")
    if item.status == "succeeded":
        previous = {"teacher_replacements": {}, "identity_confirmed": False, "changes_confirmed": False, **item.confirmation}
        if previous != payload:
            raise ApiError(409, "ROSTER_ALREADY_CONFIRMED", "该批次已完成，不能更改保留 / 放弃选择。")
        return view(item)
    if item.status != "ready" or item.revision != body.expected_revision:
        raise ApiError(409, "ROSTER_NOT_READY", "请修正全部错误后重新上传并预校验。")
    checked = await preflight(db, actor.school_id, item.kind, item.rows)
    if not checked["ok"]:
        item.report, item.status = checked, "invalid"
        item.revision += 1
        audit(db, actor, "roster.preflight", item, {"kind": item.kind, "error_rows": len(checked["issues"])})
        await db.commit()
        raise ApiError(409, "ROSTER_CHANGED", "确认前复校验未通过，本批次未写入任何档案；请下载错误清单，全部修正后整表重新上传。")
    if comparable_suspects(checked["suspicious"]) != comparable_suspects(item.report["suspicious"]):
        raise ApiError(409, "DUPLICATES_CHANGED", "疑似重复名单已变化，请重新上传并逐条确认。")
    suspects = {r["row_number"] for r in checked["suspicious"]}
    if set(body.duplicate_decisions) != suspects:
        noun = "教师" if item.kind == "teachers" else "学生"
        raise ApiError(422, "DUPLICATE_CONFIRMATION_REQUIRED", f"请逐条确认全部疑似重复{noun}保留或放弃。")
    classes = (await db.scalars(select(ImportedClass).where(ImportedClass.school_id == actor.school_id, ImportedClass.status == "active"))).all() if item.kind == "students" else []
    student_passwords = await student_password_hashes(item.rows) if item.kind == "students" else {}
    imported, skipped, unresolved, changed = [], [], [], 0
    for row in item.rows:
        number, values = row["row_number"], row["values"]
        if body.duplicate_decisions.get(number) is False:
            skipped.append(number)
            continue
        teacher = item.kind == "teachers"
        username = values["教师账号" if teacher else "账号"].strip()
        must_change_password = True
        password_hash = student_passwords.get(number)
        if password_hash is None:
            password_hash = await run_in_threadpool(get_password_hash, username)
        contact = values["手机号码" if teacher else "手机号"]
        user = User(id=uuid4(), school_id=actor.school_id, username=username, account_type="teacher" if teacher else "student", password_hash=password_hash, display_name=values["教师姓名" if teacher else "姓名"].strip(), must_change_password=must_change_password, phone=(contact or None) if teacher or len(contact) <= 100 else None)
        db.add(user)
        await db.flush()
        if teacher:
            duties = duty_codes(values)
            await grant_roles(db, user, duties)
            profile = TeacherProfile(id=user.id, school_id=actor.school_id, fields=values, duties=duties)
            db.add(profile)
            refs = await teacher_grants(db, user, values, duties)
            if refs:
                unresolved.append({"row_number": number, "references": refs})
            record_id = user.id
        else:
            await grant_roles(db, user, ["STUDENT"])
            classroom = await resolve_student_class(db, actor.school_id, values, classes)
            student = Student(
                id=uuid4(),
                school_id=actor.school_id,
                user_id=user.id,
                name=user.display_name,
                student_no=values["学号"].strip() or None,
                external_student_id=str(user.id),
                class_id=classroom.id if classroom else None,
                external_class_id=classroom.external_class_id if classroom else None,
                source_system="roster_excel",
                profile_fields=values,
            )
            db.add(student)
            await db.flush()
            from app.services import student_roster
            school = await student_roster.school(db, actor.school_id)
            if not school.current_academic_year:
                school.current_academic_year = student_roster.current_year(school)
            await student_roster.year_record(db, student, student_roster.current_year(school), values)
            record_id = student.id
        imported.append({"row_number": number, "id": str(record_id), "platform_id": str(user.platform_id if teacher else student.platform_id), "account": username})
    item.status, item.confirmed_at, item.confirmation = "succeeded", now(), payload
    operator = await db.get(User, actor.user_id)
    item.report = {**checked, "success_count": len(imported), "skipped_count": len(skipped), "skipped_rows": skipped, "imported": imported, "changed_count": changed, "unresolved_teaching": unresolved, "confirmed_by": str(actor.user_id), "confirmed_by_name": operator.display_name or operator.username, "confirmed_at": item.confirmed_at.isoformat()}
    audit(db, actor, "roster.import", item, {"kind": item.kind, "success_count": len(imported), "skipped_rows": skipped, "changed_count": changed})
    await db.commit()
    return view(item)


def comparable_suspects(value):
    """Adding immutable ID display metadata does not invalidate an old preview."""
    if isinstance(value, list):
        return [comparable_suspects(item) for item in value]
    if isinstance(value, dict):
        return {key: comparable_suspects(item) for key, item in value.items() if key != "platform_id"}
    return value


def errors_excel(item):
    headers = ERROR_COLUMNS if item.kind == "teachers" else [h.replace("教师姓名", "姓名").replace("教师账号", "账号") for h in ERROR_COLUMNS]
    rows = [[f"行{i['row_number']}" if i["row_number"] else "文件", i["error_type"], i["fields"], i["name"], i["account"], i["message"], i["original"], i["suggestion"]] for i in item.report.get("issues", [])]
    return workbook_bytes(headers, rows)


async def listing(db, actor, kind, search="", phone="", class_name="", page=1, page_size=30):
    classes = {c.id: c for c in (await db.scalars(select(ImportedClass).where(ImportedClass.school_id == actor.school_id))).all()}
    items = []
    if kind == "teachers":
        rows = (await db.execute(select(User, TeacherProfile).outerjoin(TeacherProfile, TeacherProfile.id == User.id).where(User.school_id == actor.school_id, User.status != "deleted", User.id.in_(role_users(actor.school_id, "TEACHER"))).order_by(User.created_at.desc(), User.id))).all()
        grants = (await db.execute(select(TeachingAssignment.teacher_user_id, ImportedClass.name).join(ImportedClass, ImportedClass.id == TeachingAssignment.class_id).where(TeachingAssignment.school_id == actor.school_id))).all()
        grants_by_teacher = {}
        for teacher_id, name in grants:
            grants_by_teacher.setdefault(teacher_id, set()).add(name)
        for user, profile in rows:
            fields = (profile.fields or {}) if profile else {**dict.fromkeys(TEACHER_COLUMNS, ""), "教师姓名": user.display_name or user.username, "教师账号": user.username, "手机号码": user.phone or "", "状态": "正常"}
            # Imported profiles show the workbook cell. Leadership grants can cover
            # an entire grade and must not be presented as classes taught in Excel.
            display_class = fields.get("任课年级班级", "") if profile else "、".join(sorted(grants_by_teacher.get(user.id, ())))
            items.append({**data(user, "id", "username", "status", "display_name"), "platform_id": str(user.platform_id), "name": user.display_name, "phone": fields.get("手机号码", user.phone or ""), "class_name": display_class, "fields": fields, "duties": profile.duties if profile else ["TEACHER"]})
    else:
        rows = (await db.execute(select(Student, User).outerjoin(User, User.id == Student.user_id).where(Student.school_id == actor.school_id).order_by(Student.created_at.desc(), Student.id))).all()
        for student, user in rows:
            classroom = classes.get(student.class_id) or next((c for c in classes.values() if c.external_class_id == student.external_class_id), None)
            fields = student.profile_fields or {}
            saved_class_name = f"{_student_text(fields.get('年级（1-12）'))}{_student_text(fields.get('班级号'))}"
            items.append({**data(student, "id", "name", "status", "user_id", "student_no", "source_system"), "username": user.username if user else "", "phone": fields.get("手机号", ""), "class_name": classroom.name if classroom else saved_class_name, "fields": fields})
    filtered = [i for i in items if (not search or search in (i["name"] or "") or search in i["username"] or search in i.get("platform_id", "") or (kind == "teachers" and search in i["phone"])) and (not phone or phone in i["phone"]) and (not class_name or class_name in i["class_name"] or class_name in i["fields"].get("任课年级班级", ""))]
    return {"items": filtered[(page - 1) * page_size:page * page_size], "total": len(filtered), "page": page, "page_size": page_size}


def deletion_view(snapshot):
    return {**data(snapshot, "id", "user_id", "teacher_name", "account", "fields", "duties", "deleted_by", "operator_name", "deleted_at", "reimported_user_id", "reimported_at", "reason", "reason_note", "operation_id", "task_id", "updated_fields"), "platform_id": str(snapshot.platform_id), "task_status": ("succeeded" if snapshot.reimported_at else "pending") if snapshot.task_id else None}


async def deletion_history(db, actor, search="", available=False, page=1, page_size=30, reason=""):
    query = select(TeacherDeletion).where(TeacherDeletion.school_id == actor.school_id)
    if search:
        from sqlalchemy import cast, String
        try:
            identifier = UUID(search)
        except ValueError:
            identifier = None
        query = query.where(or_(cast(TeacherDeletion.platform_id, String).contains(search, autoescape=True), TeacherDeletion.teacher_name.contains(search, autoescape=True), TeacherDeletion.account.contains(search, autoescape=True), TeacherDeletion.operation_id == identifier if identifier else cast(TeacherDeletion.operation_id, String).contains(search, autoescape=True), TeacherDeletion.task_id == identifier if identifier else cast(TeacherDeletion.task_id, String).contains(search, autoescape=True), TeacherDeletion.task_id.in_(select(RosterImport.change_task_id).where(RosterImport.school_id == actor.school_id, or_(RosterImport.filename.contains(search, autoescape=True), RosterImport.id == identifier if identifier else cast(RosterImport.id, String).contains(search, autoescape=True))))))
    if reason:
        query = query.where(TeacherDeletion.reason == reason)
    if available:
        query = query.where(TeacherDeletion.task_id.is_not(None), TeacherDeletion.reimported_user_id.is_(None))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await db.scalars(query.order_by(TeacherDeletion.deleted_at.desc(), TeacherDeletion.id).offset((page - 1) * page_size).limit(page_size))).all()
    return {"items": [deletion_view(row) for row in rows], "total": total, "page": page, "page_size": page_size}


async def deletion_detail(db, actor, identifier):
    snapshot = await owned(db, TeacherDeletion, identifier, actor)
    grants = (await db.execute(select(TeachingAssignment, ImportedClass.name, Subject.name).join(ImportedClass, ImportedClass.id == TeachingAssignment.class_id).join(Subject, Subject.id == TeachingAssignment.subject_id).where(TeachingAssignment.school_id == actor.school_id, TeachingAssignment.teacher_user_id == snapshot.user_id).order_by(TeachingAssignment.starts_at, TeachingAssignment.id))).all()
    return {**deletion_view(snapshot), "teaching_history": [{**data(grant, "id", "status", "starts_at", "expires_at"), "class_name": classroom, "subject_name": subject} for grant, classroom, subject in grants]}


async def references(db, table_name, identifier, skip=()):
    """Inspect real FK references, including future score/history tables, before deletion."""
    found = set()
    for table in Base.metadata.sorted_tables:
        if table.name in skip:
            continue
        for column in table.columns:
            if any(fk.column.table.name == table_name and fk.column.name == "id" for fk in column.foreign_keys):
                if await db.scalar(select(func.count()).select_from(table).where(column == identifier)):
                    found.add(table.name)
    return sorted(found)


async def lifecycle(db, actor, kind, identifier, body):
    if kind == "teachers":
        raise ApiError(422, "TEACHER_DELETE_REASON_REQUIRED", "请在教师列表核对完整档案并选择删除原因。资料变更会建立专属任务。")
    await owned(db, Student, identifier, actor)
    raise ApiError(422, "STUDENT_WORKFLOW_REQUIRED", "请在学生档案页通过离校办理或误导入删除核对身份、预览影响并整批确认；学生资料有误须走专用变更流程。")
