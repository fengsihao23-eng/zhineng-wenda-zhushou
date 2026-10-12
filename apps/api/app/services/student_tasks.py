"""Durable, tenant-scoped and atomic student maintenance workflows (r79)."""
import base64
from collections import Counter
from uuid import UUID
from sqlalchemy import select, or_
from app.core.errors import ApiError
from app.db.models import (Student, User, Role, UserRole, StudentYearClass, StudentWorkflowTask, RosterImport)
from app.services.education_common import owned, claim, digest, audit, now
from app.services.roster_excel import (STUDENT_COLUMNS, STUDENT_CHANGE_COLUMNS, STUDENT_LOCKED_FIELDS,
                                      STUDENT_PROMOTION_COLUMNS, STUDENT_ERROR_COLUMNS,
                                      parse_excel, workbook_bytes, file_issue)
from app.services import student_roster as roster

TERMINAL = {"succeeded", "cancelled", "rejected"}


def issue(row, message, fields="学生ID", type_="字段错误"):
    values = row.get("values", {})
    return {"row_number": row.get("row_number"), "student_id": values.get("学生ID", ""),
            "error_type": type_, "fields": fields, "name": values.get("姓名", "—"),
            "account": values.get("账号", "—"), "message": message,
            "original": "、".join(str(values.get(field, "（空）")) for field in fields.split("、")),
            "suggestion": "核对原档案与名单，修正后重新办理；身份存疑请提交审核"}


async def identifiers(db, school_id, rows):
    from app.services.person_ids import resolve
    return await resolve(db, school_id, "student", [row["values"].get("学生ID", "") for row in rows])


def editable(task, revision):
    if task.status in TERMINAL:
        raise ApiError(409, "STUDENT_TASK_FINISHED", "该办理任务已结束，请查看办理记录。")
    if task.revision != revision:
        raise ApiError(409, "STUDENT_TASK_CHANGED", "任务已更新，请刷新后重新核对。")


async def create(db, actor, body, key):
    from app.services.person_ids import normalize_body
    body = await normalize_body(db, actor.school_id, "student", body)
    school = await roster.school(db, actor.school_id, lock=True)
    payload = body.model_dump(mode="json")
    file_issues, original = [], None
    if body.kind in {"archive", "promotion"}:
        if not body.filename or body.content_base64 is None:
            raise ApiError(422, "STUDENT_FILE_REQUIRED", "请上传本次办理的 Excel 文件。")
        columns = STUDENT_CHANGE_COLUMNS if body.kind == "archive" else STUDENT_PROMOTION_COLUMNS
        rows, file_issues = parse_excel("students", body.filename, body.content_base64, columns)
        original = base64.b64decode(body.content_base64, validate=True)
    else:
        if not body.student_ids or len(set(body.student_ids)) != len(body.student_ids):
            raise ApiError(422, "STUDENT_SELECTION_REQUIRED", "请选择办理对象，学生ID不可重复。")
        if body.kind == "identity" and (len(body.student_ids) != 1 or body.field is None or not body.new_value.strip() or not body.reason.strip()):
            raise ApiError(422, "SINGLE_CHANGE_REQUIRED", "姓名或账号每次仅变更一项，须填写新值和变更原因。")
        if body.kind == "status" and body.action is None:
            raise ApiError(422, "STUDENT_ACTION_REQUIRED", "请选择离校、应届毕业或恢复在读，每批只办理一种。")
        if body.kind == "deletion" and not body.reason.strip():
            raise ApiError(422, "DELETE_REASON_REQUIRED", "请填写误导入或多余记录的核实依据。")
        matches = await roster.people(db, actor.school_id, body.student_ids)
        if len(matches) != len(body.student_ids):
            raise ApiError(404, "RESOURCE_NOT_AVAILABLE", "名单包含不存在或不在授权范围内的学生。")
        classes = await roster.class_map(db, actor.school_id)
        rows = [{"row_number": index + 2, "values": roster.fields31(s, u, school, classes)} for index, (s, u) in enumerate(matches)]
    identifier, fresh = await claim(db, actor, "student.workflow.create", key, payload)
    if not fresh:
        return roster.task_view(await owned(db, StudentWorkflowTask, identifier, actor))
    scoped_rows = await roster.people(db, actor.school_id, (await identifiers(db, actor.school_id, rows)).values())
    classes = await roster.class_map(db, actor.school_id)
    snapshots = []
    imported = (await db.execute(select(RosterImport.id, RosterImport.report, RosterImport.original_content.is_not(None)).where(
        RosterImport.school_id == actor.school_id, RosterImport.kind == "students", RosterImport.status == "succeeded"))).all()
    sources = {row["id"]: (str(batch_id), has_original) for batch_id, report, has_original in imported for row in report.get("imported", [])}
    for student, user in scoped_rows:
        fields = roster.fields31(student, user, school, classes)
        snapshots.append({"id": str(student.id), "platform_id": str(student.platform_id), "fields": fields, "fingerprint": roster.fingerprint(student, user, fields),
                          "source_import_id": sources.get(str(student.id), (None, False))[0],
                          "source_import_has_original": sources.get(str(student.id), (None, False))[1],
                          "created_at": student.created_at.isoformat(),
                          "user_id": str(user.id) if user else None})
    operator = await db.get(User, actor.user_id)
    payload.pop("content_base64", None)
    payload["current_year_at_creation"] = roster.current_year(school)
    if body.kind in {"promotion", "status"}:
        payload["target_year"] = body.target_year or (roster.year_after(roster.current_year(school)) if body.mode == "next" else roster.current_year(school))
    task = StudentWorkflowTask(id=identifier, school_id=actor.school_id, kind=body.kind, rows=rows,
                               snapshots=snapshots, request_payload=payload, filename=body.filename,
                               original_content=original, report={"file_issues": file_issues},
                               created_by=actor.user_id, operator_name=(operator.display_name or operator.username))
    db.add(task)
    await db.flush()
    task.report = await evaluate(db, actor, task)
    set_status(task)
    audit(db, actor, f"student.{task.kind}.preview", task, {"students": len(snapshots), "errors": len(task.report["issues"])})
    await db.commit()
    return roster.task_view(task)


def set_status(task):
    if task.status in TERMINAL:
        return
    task.status = "invalid" if task.report["issues"] else "pending_review" if task.report["pending_review_ids"] else "ready"


async def evaluate(db, actor, task):
    school = await roster.school(db, actor.school_id)
    classes = await roster.class_map(db, actor.school_id)
    current, payload, prepared = roster.current_year(school), task.request_payload, task.preparation or {}
    resolved = await identifiers(db, actor.school_id, task.rows)
    people = {str(s.id): (s, u) for s, u in await roster.people(db, actor.school_id, resolved.values())}
    snapshots = {row["id"]: row for row in task.snapshots}
    report = {"file_issues": task.report.get("file_issues", []), "issues": list(task.report.get("file_issues", [])),
              "changes": [], "placements": [], "anomalies": [], "duplicates": [], "missing": [],
              "graduation_candidates": [], "pending_graduations": [], "pending_review_ids": [],
              "affected": [], "affected_exams": [], "identity_rows": [], "total_rows": len(task.rows),
              "current_year": current, "target_year": payload.get("target_year"), "ready_to_confirm": False}
    canonical = lambda row: str(resolved.get(row["values"].get("学生ID", ""), row["values"].get("学生ID", "")))
    counts = Counter(canonical(row) for row in task.rows)
    confirmed = set(prepared.get("identity_confirmed_ids", []))
    uncertain = set(prepared.get("identity_uncertain_ids", []))
    approvals = prepared.get("anomaly_approvals", {})
    seen = set()
    for row in task.rows:
        values = row["values"]
        sid = canonical(row)
        if counts[sid] > 1:
            lines = [str(item["row_number"]) for item in task.rows if canonical(item) == sid]
            report["issues"].append(issue(row, "学生ID在第 " + "、".join(lines) + " 行重复；全部重复行须修正", type_="ID重复"))
        if sid not in people:
            report["issues"].append(issue(row, "学生ID必填，须存在且属于本校；不得手工编造或使用其他学校的ID", type_="ID缺失或不存在"))
            continue
        student, user = people[sid]
        original = roster.fields31(student, user, school, classes)
        if sid not in seen:
            report["identity_rows"].append({"id": sid, "platform_id": str(student.platform_id), "name": student.name, "account": original["账号"],
                                            "student_no": student.student_no, "registration_no": original["学籍号"],
                                            "grade": original["年级（1-12）"], "class_number": original["班级号"],
                                            "source_import_id": snapshots.get(sid, {}).get("source_import_id"),
                                            "source_import_has_original": snapshots.get(sid, {}).get("source_import_has_original", False)})
            seen.add(sid)
        if snapshots.get(sid, {}).get("fingerprint") != roster.fingerprint(student, user, original):
            report["issues"].append(issue(row, "原档案或账号状态已变化，请重新导出资料或重新办理", type_="原记录已变化"))
        review = (task.reviews or {}).get(sid, {})
        if review.get("status") == "pending" or (sid in uncertain and review.get("status") != "approved"):
            report["pending_review_ids"].append(sid)
        if task.kind == "archive":
            if student.status != "active":
                report["issues"].append(issue(row, "档案变更仅限状态为正常的学生", "状态", "状态非法"))
            for field in STUDENT_LOCKED_FIELDS:
                if field != "学生ID" and values.get(field) != original[field]:
                    report["issues"].append(issue(row, f"锁定字段【{field}】与原记录不一致；请使用对应办理入口", field, "锁定字段不一致"))
            for field in STUDENT_COLUMNS:
                if field not in STUDENT_LOCKED_FIELDS and values.get(field, "") != original[field]:
                    report["changes"].append({"student_id": sid, "platform_id": str(student.platform_id), "name": student.name, "account": original["账号"],
                                              "field": field, "before": original[field], "after": values.get(field, ""),
                                              "clear": not values.get(field, ""), "row_number": row["row_number"]})
        elif task.kind == "identity":
            await evaluate_identity(db, actor, task, report, row, student, user, original)
        elif task.kind in {"promotion", "status"}:
            await evaluate_placement(db, actor, task, report, row, student, user, original, approvals)
        elif task.kind == "deletion":
            if student.status != "active":
                report["issues"].append(issue(row, "误导入删除仅限状态为正常的误导入或多余记录；离校、毕业档案须保留", "状态", "状态非法"))
            if user and user.id == actor.user_id:
                report["issues"].append(issue(row, "不能删除当前操作账号"))
            if payload["deletion_type"] == "duplicate":
                kept = payload.get("retained_students", {}).get(sid)
                try:
                    kept_id = UUID(kept or "")
                except ValueError:
                    kept_id = None
                retained = await db.scalar(select(Student).where(Student.school_id == actor.school_id, Student.id == kept_id)) if kept_id else None
                if retained is None or str(retained.id) in counts or retained.created_at > student.created_at:
                    report["issues"].append(issue(row, "重复记录须指定最早创建且已核实有效的保留记录；保留记录不得在删除名单中"))
    if task.kind == "promotion" and payload["mode"] == "next":
        await evaluate_switch(db, actor, task, report, counts)
    if task.kind == "deletion" and task.rows and not report["issues"]:
        from app.services.student_data import deletion_preview
        impact = await deletion_preview(db, actor, [s for s, _ in people.values()])
        report.update(impact)
        if impact["deletion_barriers"]:
            report["issues"].append(file_issue("原账号还参与共享业务记录，须先移交后办理；相关表：" + "、".join(impact["deletion_barriers"])))
    if task.kind in {"promotion", "status"} and payload.get("current_year_at_creation") != current:
        report["issues"].append(file_issue("学校当前学年已变化，请重新选择学年并上传名单。"))
    approval_ids = {row["student_id"] for row in report["anomalies"]}
    approvals_ready = all(sid in approvals and str(approvals[sid]).strip() for sid in approval_ids)
    identities_ready = bool(seen) and all(sid in confirmed or (task.reviews or {}).get(sid, {}).get("status") == "approved" for sid in seen)
    deletion_ready = task.kind != "deletion" or seen.issubset(set(prepared.get("records_verified_ids", [])))
    duplicate_ready = not report["duplicates"] or prepared.get("duplicate_name_confirmed", False)
    switch_ready = task.kind != "promotion" or payload["mode"] != "next" or (prepared.get("graduation_confirmed", False) and not report["pending_graduations"] and not report["missing"] and not report.get("graduation_exclusions_missing"))
    report["ready_to_confirm"] = bool(task.rows) and not report["issues"] and not report["pending_review_ids"] and identities_ready and deletion_ready and duplicate_ready and approvals_ready and switch_ready
    report["identity_confirmed"] = identities_ready
    report["anomalies_approved"] = approvals_ready
    report["affected_students"] = len({r["student_id"] for r in report["changes"]}) if task.kind == "archive" else len(seen)
    report["clear_count"] = sum(row["clear"] for row in report["changes"])
    return report


async def evaluate_identity(db, actor, task, report, row, student, user, original):
    payload = task.request_payload
    field, new_value = payload["field"], payload["new_value"].strip()
    if student.status != "active" or user is None:
        report["issues"].append(issue(row, "姓名或账号变更仅限正常在读且已绑定账号的学生", "状态"))
    if new_value == original[field]:
        report["issues"].append(issue(row, "新值与原值相同，无需办理", field))
    if field == "账号":
        from app.services.roster_workbench import role_users
        scope = or_(User.account_type == "student", User.id.in_(role_users(actor.school_id, "STUDENT")),
                    User.id.in_(select(Student.user_id).where(Student.school_id == actor.school_id, Student.user_id.is_not(None))))
        conflict = await db.scalar(select(User.id).where(User.school_id == actor.school_id, User.id != (user.id if user else None),
                                                       User.username == new_value, User.status != "deleted", scope))
        if conflict:
            report["issues"].append(issue(row, "新账号已被其他学生占用，请重新输入；教师和家长账号空间独立", "账号", "账号重复"))
        if user:
            other_roles = (await db.scalars(select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id, Role.code != "STUDENT"))).all()
            if other_roles and user.account_type != "student":
                report["issues"].append(issue(row, "原账号关联多个账号类型，请先核对独立学生身份，避免更改其他身份账号", "账号"))
    else:
        all_people = await roster.people(db, actor.school_id)
        classes = await roster.class_map(db, actor.school_id)
        school = await roster.school(db, actor.school_id)
        for other, other_user in all_people:
            values = roster.fields31(other, other_user, school, classes)
            if other.id != student.id and other.name == new_value and values["年级（1-12）"] == original["年级（1-12）"] and values["班级号"] == original["班级号"]:
                report["duplicates"].append({"student_id": str(other.id), "platform_id": str(other.platform_id), "name": other.name, "account": values["账号"],
                                              "grade": values["年级（1-12）"], "class_number": values["班级号"]})
    report["changes"].append({"student_id": str(student.id), "platform_id": str(student.platform_id), "name": student.name, "account": original["账号"],
                              "field": field, "before": original[field], "after": new_value, "clear": False})


async def evaluate_placement(db, actor, task, report, row, student, user, original, approvals):
    payload, sid = task.request_payload, str(student.id)
    year = payload["target_year"]
    current = report["current_year"]
    if year not in {current, roster.year_after(current)} or (task.kind == "promotion" and year != (current if payload["mode"] == "current" else roster.year_after(current))):
        report["issues"].append(issue(row, "仅可选择当前学年或紧接的下一学年，并与办理分支一致", "目标学年"))
    is_restore = task.kind == "status" and payload["action"] == "restore"
    if is_restore:
        if student.status not in {"departed", "graduated", "suspended", "withdrawn", "inactive"} or user is None:
            report["issues"].append(issue(row, "恢复在读仅限已离校或毕业、保留原账号的学生", "状态"))
    elif student.status != "active" or (task.kind == "promotion" and (user is None or user.status != "active")):
        report["issues"].append(issue(row, "本次办理仅限学籍状态正常的学生；升级换班还须原账号已启用", "状态、账号"))
    if task.kind == "promotion":
        target_grade, target_class = row["values"].get("目标年级", "").strip(), row["values"].get("目标班级号", "").strip()
        for field in STUDENT_PROMOTION_COLUMNS:
            if not row["values"].get(field, "").strip():
                report["issues"].append(issue(row, f"【{field}】必填", field, "必填缺失"))
        for field in ("姓名", "账号"):
            if row["values"].get(field) != original[field]:
                report["issues"].append(issue(row, f"【{field}】与学生ID对应的原记录不一致", field, "身份不一致"))
    else:
        place = payload.get("placements", {}).get(sid, {})
        target_grade, target_class = place.get("grade", original["年级（1-12）"]).strip(), place.get("class_number", original["班级号"]).strip()
    is_move = task.kind == "promotion" or is_restore
    if is_move and (target_grade not in set(roster.GRADE_NAMES.values()) | {"复读班", "高中复读班"} or not target_class or len(target_grade + target_class) > 100):
        report["issues"].append(issue(row, "目标年级须填写完整年级名称（如高中一年级），目标班级须填写班级名称（如1班）", "目标年级、目标班级号"))
    records = (await db.scalars(select(StudentYearClass).where(StudentYearClass.school_id == actor.school_id,
                                                              StudentYearClass.student_id == student.id).order_by(StudentYearClass.academic_year.desc()))).all()
    record = next((item for item in records if item.academic_year == year), None)
    if task.kind == "status" and not is_restore and record:
        target_grade, target_class = record.grade, record.class_number
    recent = next((item for item in records if item.academic_year <= current and item.grade), None)
    old_grade = recent.grade if recent else original["年级（1-12）"]
    if task.kind == "status" and payload["action"] == "graduate":
        if not roster.graduating(record.grade if record else target_grade):
            report["issues"].append(issue(row, "应届毕业须属于所选学年本学段毕业年级（小学六年级、初中三年级、高中三年级或复读班），须核对实际毕业名单", "年级（1-12）"))
    if is_restore:
        source_segment = roster.segment(old_grade) or payload.get("placements", {}).get(sid, {}).get("source_segment")
        if not source_segment or source_segment != roster.segment(target_grade):
            report["issues"].append(issue(row, "恢复在读仅限同学段返校；原学段不明须人工核实，跨学段入学请走新增导入", "目标年级"))
    if is_move:
        old_rank, new_rank = roster.grade_rank(old_grade), roster.grade_rank(target_grade)
        normal = old_rank is not None and new_rank == old_rank + (1 if year != current else 0)
        if not normal:
            report["anomalies"].append({"student_id": sid, "platform_id": str(student.platform_id), "name": student.name, "account": original["账号"],
                                        "before": old_grade, "after": target_grade,
                                        "message": "缺少年级依据，须核实" if old_rank is None else "非顺升一级" if year != current else "当前学年年级改变",
                                        "approval": approvals.get(sid, "")})
    target_status = "active" if is_move else "graduated" if payload["action"] == "graduate" else "departed"
    report["placements"].append({"student_id": sid, "platform_id": str(student.platform_id), "name": student.name, "account": original["账号"],
                                 "target_year": year, "old_grade": original["年级（1-12）"], "old_class": original["班级号"],
                                 "grade": target_grade, "class_number": target_class, "operation": "更新" if record else "新增",
                                 "before_status": student.status, "target_status": target_status,
                                 "account_enabled": is_move, "archived": target_status == "graduated"})


async def evaluate_switch(db, actor, task, report, ids):
    prepared = task.preparation or {}
    school, classes = await roster.school(db, actor.school_id), await roster.class_map(db, actor.school_id)
    all_rows = await roster.people(db, actor.school_id)
    active_ids = {str(s.id) for s, _ in all_rows if s.status == "active"}
    actual_graduates = set(prepared.get("graduation_student_ids", []))
    exclusions = prepared.get("graduation_exclusions", {})
    report["graduation_exclusions_missing"] = []
    valid_grad_ids = set()
    for student, user in all_rows:
        values = roster.fields31(student, user, school, classes)
        sid = str(student.id)
        if roster.graduating(values["年级（1-12）"]) and (student.status == "active" or sid in actual_graduates):
            entry = {"student_id": sid, "platform_id": str(student.platform_id), "name": student.name, "account": values["账号"], "grade": values["年级（1-12）"],
                     "class_number": values["班级号"], "status": student.status}
            report["graduation_candidates"].append(entry)
            valid_grad_ids.add(sid)
            if sid in actual_graduates and student.status != "graduated":
                report["pending_graduations"].append(entry)
            elif student.status == "active" and sid not in actual_graduates and not str(exclusions.get(sid, "")).strip():
                report["graduation_exclusions_missing"].append(entry)
    if not actual_graduates.issubset(valid_grad_ids):
        report["issues"].append(file_issue("实际毕业名单包含不属于本校毕业候选范围的学生，请重新核实。"))
    for student, user in all_rows:
        sid = str(student.id)
        if sid in active_ids and sid not in ids and sid not in actual_graduates:
            values = roster.fields31(student, user, school, classes)
            report["missing"].append({"student_id": sid, "platform_id": str(student.platform_id), "name": student.name, "account": values["账号"],
                                      "grade": values["年级（1-12）"], "class_number": values["班级号"]})


async def prepare(db, actor, identifier, body):
    from app.services.person_ids import normalize_body
    body = await normalize_body(db, actor.school_id, "student", body)
    task = await owned(db, StudentWorkflowTask, identifier, actor, lock=True)
    editable(task, body.expected_revision)
    ids = {snapshot["id"] for snapshot in task.snapshots}
    confirmed, uncertain = {str(s) for s in body.identity_confirmed_ids}, {str(s) for s in body.identity_uncertain_ids}
    verified = {str(s) for s in body.records_verified_ids}
    if not (confirmed | uncertain | verified).issubset(ids) or confirmed.intersection(uncertain):
        raise ApiError(422, "IDENTITY_SELECTION_INVALID", "身份核对名单不属于本任务，或同一学生被同时标为已核实和存疑。")
    for values in (body.anomaly_approvals, body.graduation_exclusions):
        if any(not value.strip() or len(value) > 500 for value in values.values()):
            raise ApiError(422, "REVIEW_BASIS_REQUIRED", "每条异常审批或非毕业剔除记录须填写核实依据（最多500字）。")
    reviews = dict(task.reviews or {})
    for sid in uncertain:
        if reviews.get(sid, {}).get("status") not in {"approved", "rejected"}:
            reviews[sid] = {"status": "pending", "submitted_by": str(actor.user_id), "submitted_at": now().isoformat()}
    task.reviews = reviews
    task.preparation = {**body.model_dump(mode="json", exclude={"expected_revision"}),
                        "prepared_by": str(actor.user_id), "prepared_at": now().isoformat()}
    task.report = await evaluate(db, actor, task)
    valid_anomalies = {row["student_id"] for row in task.report["anomalies"]}
    if not {str(s) for s in body.anomaly_approvals}.issubset(valid_anomalies):
        raise ApiError(422, "ANOMALY_SELECTION_INVALID", "审批记录不属于本次年级异常清单。")
    task.revision += 1
    set_status(task)
    audit(db, actor, f"student.{task.kind}.prepare", task, {"identity_review_count": len(uncertain), "approved_anomalies": len(body.anomaly_approvals)})
    await db.commit()
    return roster.task_view(task)


async def review(db, actor, identifier, body):
    from app.services.person_ids import normalize_body
    body = await normalize_body(db, actor.school_id, "student", body)
    task = await owned(db, StudentWorkflowTask, identifier, actor, lock=True)
    editable(task, body.expected_revision)
    reviews = dict(task.reviews or {})
    if not body.note.strip() or any(reviews.get(str(s), {}).get("status") != "pending" for s in body.student_ids):
        raise ApiError(422, "PENDING_REVIEW_REQUIRED", "仅可审核本任务待审核的学生，须填写核验依据。")
    for sid in body.student_ids:
        reviews[str(sid)] = {**reviews[str(sid)], "status": body.decision,
                             "reviewer_id": str(actor.user_id), "note": body.note.strip(), "reviewed_at": now().isoformat()}
    task.reviews, task.reviewed_at = reviews, now()
    if body.decision == "rejected":
        task.status = "rejected"
    task.report = await evaluate(db, actor, task)
    task.revision += 1
    set_status(task)
    audit(db, actor, f"student.{task.kind}.identity_review", task, {"decision": body.decision, "students": [str(s) for s in body.student_ids], "note": body.note.strip()})
    await db.commit()
    return roster.task_view(task)


async def cancel(db, actor, identifier, body):
    task = await owned(db, StudentWorkflowTask, identifier, actor, lock=True)
    if task.status == "cancelled":
        return roster.task_view(task)
    editable(task, body.expected_revision)
    task.status, task.revision = "cancelled", task.revision + 1
    audit(db, actor, f"student.{task.kind}.cancel", task)
    await db.commit()
    return roster.task_view(task)


async def confirm(db, actor, identifier, body):
    task = await owned(db, StudentWorkflowTask, identifier, actor, lock=True)
    if task.status == "succeeded":
        if task.confirmation != body.model_dump(mode="json"):
            raise ApiError(409, "STUDENT_ALREADY_CONFIRMED", "本任务已完成，不能更改确认内容。")
        return roster.task_view(task)
    editable(task, body.expected_revision)
    school = await roster.school(db, actor.school_id, lock=True)
    resolved = await identifiers(db, actor.school_id, task.rows)
    locked_people = await roster.people(db, actor.school_id, resolved.values(), lock=True)
    user_ids = [s.user_id for s, _ in locked_people if s.user_id]
    if user_ids:
        await db.execute(select(User).where(User.id.in_(user_ids)).order_by(User.id).with_for_update().execution_options(populate_existing=True))
    task.report = await evaluate(db, actor, task)
    set_status(task)
    if not task.report["ready_to_confirm"]:
        task.revision += 1
        await db.commit()
        raise ApiError(409, "STUDENT_CONFIRMATION_BLOCKED", "确认前复校验未通过：请核对错误、身份审核、名单完整性及年级审批。本批未更新任何学生。", details={"task_id": str(task.id)})
    people = {str(s.id): (s, u) for s, u in locked_people}
    if not school.current_academic_year:
        school.current_academic_year = roster.current_year(school)
    if task.kind == "deletion":
        from app.services.student_data import delete_student_data
        task.report["disposition"] = await delete_student_data(db, actor, [s for s, _ in locked_people], task.report)
    elif task.kind == "archive":
        for row in task.rows:
            student, user = people[str(resolved[row["values"]["学生ID"]])]
            values = dict(row["values"])
            values.pop("学生ID", None)
            student.profile_fields = values
            student.student_no = values["学号"] or None
            if user:
                user.phone = values["手机号"] if len(values["手机号"]) <= 100 else None
    elif task.kind == "identity":
        student, user = next(iter(people.values()))
        payload, fields = task.request_payload, dict(student.profile_fields or {})
        value = payload["new_value"].strip()
        if payload["field"] == "姓名":
            student.name, user.display_name = value, value
        else:
            user.username, user.account_type = value, "student"
            user.password_version += 1
        fields[payload["field"]] = value
        student.profile_fields = fields
    else:
        await apply_placements(db, task, school, people)
    task.status, task.confirmed_at, task.confirmation = "succeeded", now(), body.model_dump(mode="json")
    task.report = {**task.report, "success_count": task.report["affected_students"],
                   "confirmed_by": str(actor.user_id), "confirmed_by_name": (await db.get(User, actor.user_id)).display_name,
                   "confirmed_at": task.confirmed_at.isoformat()}
    audit(db, actor, f"student.{task.kind}.confirm", task, {"students": task.report["affected_students"],
                                                           "cleared_fields": task.report["clear_count"],
                                                           "target_year": task.request_payload.get("target_year")})
    await db.commit()
    return roster.task_view(task)


async def apply_placements(db, task, school, people):
    from app.services import student_roster as roster
    payload = task.request_payload
    for row in task.report["placements"]:
        student, user = people[row["student_id"]]
        classes = await roster.class_map(db, student.school_id)
        fields = roster.fields31(student, user, school, classes)
        await roster.freeze_history(db, student, fields, roster.current_year(school))
        current_record = await db.scalar(select(StudentYearClass).where(StudentYearClass.school_id == student.school_id,
                                                                       StudentYearClass.student_id == student.id,
                                                                       StudentYearClass.academic_year == roster.current_year(school)))
        if current_record is None:
            await roster.year_record(db, student, roster.current_year(school), fields)
        move = task.kind == "promotion" or payload["action"] == "restore"
        classroom = await roster.resolve_class(db, student.school_id, row["grade"], row["class_number"]) if move else None
        year_fields = {**fields, "年级（1-12）": row["grade"], "班级号": row["class_number"]}
        target_status = row["target_status"]
        fields["状态"] = roster.STATUS_LABELS[target_status]
        await roster.year_record(db, student, row["target_year"], year_fields, target_status, classroom)
        student.status = target_status
        student.archived_at = now() if target_status == "graduated" else None if move else student.archived_at
        if move:
            student.class_id, student.external_class_id = classroom.id, classroom.external_class_id
            fields["年级（1-12）"], fields["班级号"] = row["grade"], row["class_number"]
        fields.pop("学生ID", None)
        student.profile_fields = fields
        if user and user.status != target_status:
            user.status = target_status
            user.password_version += 1
    if task.kind == "promotion" and payload["mode"] == "next":
        school.current_academic_year = payload["target_year"]


def errors_excel(task):
    headers = STUDENT_ERROR_COLUMNS + ["学生ID"]
    return workbook_bytes(headers, [[f"行{row['row_number']}" if row.get("row_number") else "文件",
                                    row.get("error_type", "字段错误"), row["fields"], row["name"], row["account"],
                                    row["message"], row.get("original", ""), row["suggestion"], row.get("student_id", "—")]
                                   for row in task.report["issues"]])
