"""Teacher deletion and task-bound, atomic reconstruction with stable identities."""
import base64
from uuid import UUID, uuid4
from sqlalchemy import select, delete
from starlette.concurrency import run_in_threadpool
from app.core.errors import ApiError
from app.core.security import get_password_hash
from app.db.models.user import User, UserRole
from app.db.models.roster import TeacherProfile, TeacherDeletion, TeacherChangeTask, RosterImport
from app.db.models.teaching import TeachingAssignment
from app.services.education_common import owned, claim, audit, data, digest, now
from app.services.roster_excel import (
    TEACHER_COLUMNS, TEACHER_CHANGE_COLUMNS, parse_excel, workbook_bytes, file_issue, error_row, duty_codes,
)
from app.services import roster_workbench as roster


async def task_snapshots(db, actor, task_id, lock=False):
    query = select(TeacherDeletion).where(
        TeacherDeletion.school_id == actor.school_id, TeacherDeletion.task_id == task_id,
    ).order_by(TeacherDeletion.user_id)
    if lock:
        query = query.with_for_update()
    return (await db.scalars(query.execution_options(populate_existing=True))).all()


async def task_view(db, actor, task):
    snapshots = await task_snapshots(db, actor, task.id)
    batches = (await db.scalars(select(RosterImport).where(
        RosterImport.school_id == actor.school_id, RosterImport.change_task_id == task.id,
    ).order_by(RosterImport.created_at.desc(), RosterImport.id))).all()
    return {
        **data(task, "id", "status", "operator_name", "created_at", "completed_at", "confirmation"),
        "snapshots": [roster.deletion_view(row) for row in snapshots],
        "batches": [roster.view(row) for row in batches],
    }


async def delete_teachers(db, actor, body, key):
    from app.services.person_ids import normalize_body
    body = await normalize_body(db, actor.school_id, "teacher", body)
    if len(set(body.teacher_ids)) != len(body.teacher_ids):
        raise ApiError(422, "TEACHER_SELECTION_DUPLICATE", "所选教师不能重复。")
    note = body.reason_note.strip()
    if body.reason == "other" and not note:
        raise ApiError(422, "DELETION_NOTE_REQUIRED", "选择「其他」时须填写删除说明。")
    operation_id, fresh = await claim(db, actor, "roster.teachers.delete", key, body.model_dump(mode="json"))
    if fresh:
        originals = []
        for identifier in sorted(body.teacher_ids, key=str):
            user = await owned(db, User, identifier, actor, lock=True)
            if identifier == actor.user_id:
                raise ApiError(409, "SELF_ACCOUNT_ACTION", "不能删除当前操作账号。")
            is_teacher = user.account_type == "teacher" or await db.scalar(select(UserRole.user_id).where(
                UserRole.user_id == identifier, UserRole.user_id.in_(roster.role_users(actor.school_id, "TEACHER")),
            ))
            if not is_teacher or user.status == "deleted":
                raise ApiError(409, "TEACHER_NOT_AVAILABLE", "所选教师已删除或不可办理，请刷新列表核对。本批次未删除任何档案。")
            originals.append(user)
        operator = await db.get(User, actor.user_id)
        task = None
        if body.reason == "change":
            task = TeacherChangeTask(id=uuid4(), school_id=actor.school_id, created_by=actor.user_id,
                                     operator_name=operator.display_name or operator.username)
            db.add(task)
            await db.flush()
        for user in originals:
            profile = await db.get(TeacherProfile, user.id)
            fields = {c: (profile.fields.get(c, "") if profile else "") for c in TEACHER_COLUMNS}
            if not profile:
                fields.update({"教师姓名": user.display_name or user.username, "教师账号": user.username,
                               "手机号码": user.phone or "", "状态": "正常"})
            snapshot = TeacherDeletion(
                id=uuid4(), school_id=actor.school_id, user_id=user.id,
                teacher_name=user.display_name or user.username, account=user.username, fields=fields,
                duties=profile.duties if profile else ["TEACHER"], deleted_by=actor.user_id,
                operator_name=operator.display_name or operator.username, reason=body.reason,
                reason_note=note, operation_id=operation_id, task_id=task.id if task else None,
            )
            db.add(snapshot)
            audit(db, actor, "roster.teachers.delete", user, {
                "deletion_id": str(snapshot.id), "operation_id": str(operation_id), "reason": body.reason,
                "reason_note": note, "task_id": str(task.id) if task else None, "account": user.username,
            })
            # Release the account, invalidate tokens, retain every history FK.
            user.username, user.status = f"__deleted_teacher_{user.id.hex}", "deleted"
            user.password_version += 1
        await db.commit()
    snapshots = (await db.scalars(select(TeacherDeletion).where(
        TeacherDeletion.school_id == actor.school_id, TeacherDeletion.operation_id == operation_id,
    ).order_by(TeacherDeletion.user_id))).all()
    task_id = snapshots[0].task_id if snapshots else None
    return {
        "id": str(operation_id), "count": len(snapshots), "task_id": str(task_id) if task_id else None,
        "snapshots": [roster.deletion_view(row) for row in snapshots],
        "message": "原档案已删除、账号已释放，24 列快照已保存。" + (
            "已建立绑定原教师ID的专属变更任务，可立即上传更新文件或稍后继续。" if task_id else
            "纯删除办理完成；后续新增或复职将生成新的教师ID。"
        ),
    }


async def task_template(db, actor, identifier):
    await owned(db, TeacherChangeTask, identifier, actor)
    snapshots = await task_snapshots(db, actor, identifier)
    rows = [[row.fields.get(c, "") for c in TEACHER_COLUMNS] + [str(row.platform_id)] for row in snapshots]
    return workbook_bytes(TEACHER_CHANGE_COLUMNS, rows, lock_teacher_id=True)


async def task_preflight(db, actor, task, rows, issues=()):
    if issues:
        return {"ok": False, "issues": list(issues), "suspicious": [], "total_rows": len(rows)}
    report = await roster.preflight(db, actor.school_id, "teachers", rows)
    errors = list(report["issues"])
    snapshots = await task_snapshots(db, actor, task.id)
    from app.services.person_ids import resolve
    expected = {row.user_id for row in snapshots}
    resolved = await resolve(db, actor.school_id, "teacher", [row["values"].get("教师ID", "") for row in rows])
    if len(rows) != len(snapshots):
        errors.append({**file_issue(f"更新行数须恰好等于任务内原教师人数（{len(snapshots)} 行），当前 {len(rows)} 行。"),
                       "error_type": "任务行数不符"})
    seen = set()
    for row in rows:
        identifier = row["values"].get("教师ID", "")
        identity = resolved.get(identifier)
        message = ""
        if not identifier:
            message = "教师ID缺失；请使用本任务下载的原档案。"
        elif identity is not None and identity in seen:
            message = "教师ID重复；每名原教师只能对应一行。"
        elif identity not in expected:
            message = "教师ID被修改或不属于当前任务；教师ID是锁定字段。"
        seen.add(identity)
        if message:
            errors.append(error_row(row, ["教师ID非法"], ["教师ID"], [message], ["重新下载任务原档案，保留教师ID后修改资料并整表重传"], "teachers"))
    return {**report, "ok": not errors, "issues": errors, "task_id": str(task.id)}


async def upload_task(db, actor, identifier, body, key):
    task = await owned(db, TeacherChangeTask, identifier, actor, lock=True)
    if task.status != "pending":
        raise ApiError(409, "TEACHER_TASK_COMPLETED", "该变更任务已完成，不能再次导入。")
    rows, issues = parse_excel("teachers", body.filename, body.content_base64, TEACHER_CHANGE_COLUMNS)
    batch_id, fresh = await claim(db, actor, f"roster.teacher.task.upload.{task.id}", key, body.model_dump())
    if fresh:
        report = await task_preflight(db, actor, task, rows, issues)
        operator = await db.get(User, actor.user_id)
        item = RosterImport(
            id=batch_id, school_id=actor.school_id, kind="teachers", filename=body.filename,
            content_hash=digest(body.content_base64), original_content=base64.b64decode(body.content_base64),
            rows=rows, report=report, status="ready" if report["ok"] else "invalid",
            created_by=actor.user_id, operator_name=operator.display_name or operator.username, change_task_id=task.id,
        )
        db.add(item)
        audit(db, actor, "roster.teacher.task.preflight", task, {"batch_id": str(batch_id), "error_rows": len(report["issues"])})
        await db.commit()
    return roster.view(await owned(db, RosterImport, batch_id, actor))


async def confirm_task_batch(db, actor, item, body):
    from app.services.person_ids import normalize_body
    body = await normalize_body(db, actor.school_id, "teacher", body)
    task = await owned(db, TeacherChangeTask, item.change_task_id, actor, lock=True)
    payload = body.model_dump(mode="json")
    if item.status == "succeeded":
        if item.confirmation != payload:
            raise ApiError(409, "ROSTER_ALREADY_CONFIRMED", "该任务批次已完成，不能修改对应关系。")
        return roster.view(item)
    if task.status != "pending" or item.status != "ready" or item.revision != body.expected_revision:
        raise ApiError(409, "TEACHER_TASK_NOT_READY", "任务已完成或批次不可提交，请重新核对任务。")
    checked = await task_preflight(db, actor, task, item.rows)
    if not checked["ok"]:
        item.report, item.status = checked, "invalid"
        item.revision += 1
        await db.commit()
        raise ApiError(409, "ROSTER_CHANGED", "确认前复校验失败，本次未写入资料。变更任务已保留，请修正后重传。")
    if roster.comparable_suspects(checked["suspicious"]) != roster.comparable_suspects(item.report["suspicious"]):
        raise ApiError(409, "DUPLICATES_CHANGED", "疑似重复提醒发生变化，请重新上传核对。任务已保留。")
    suspects = {r["row_number"] for r in checked["suspicious"]}
    if set(body.duplicate_decisions) != suspects or any(not keep for keep in body.duplicate_decisions.values()):
        raise ApiError(422, "TASK_DUPLICATE_REVIEW_REQUIRED", "请核对全部疑似重复提醒；变更任务不允许单行放弃。")
    if not body.identity_confirmed or not body.changes_confirmed:
        raise ApiError(422, "TASK_CONFIRMATION_REQUIRED", "须核实新旧教师身份、对应关系和全部字段变更后整批确认。")
    snapshots = await task_snapshots(db, actor, task.id, lock=True)
    by_id = {row.user_id: row for row in snapshots}
    numbers = {row["row_number"] for row in item.rows}
    mapping = body.teacher_replacements
    if len(snapshots) == 1 and not mapping:
        mapping = {item.rows[0]["row_number"]: snapshots[0].user_id}
    if set(mapping) != numbers or set(mapping.values()) != set(by_id) or len(set(mapping.values())) != len(mapping):
        raise ApiError(422, "TASK_MAPPING_INVALID", "每行须指定原教师，每名原教师须且只能关联一次。请核对行号与对应关系。")
    from app.services.person_ids import resolve
    resolved = await resolve(db, actor.school_id, "teacher", [row["values"]["教师ID"] for row in item.rows])
    for row in item.rows:
        if mapping[row["row_number"]] != resolved.get(row["values"]["教师ID"]):
            raise ApiError(422, "TASK_MAPPING_ID_MISMATCH", f"第 {row['row_number']} 行对应教师与锁定教师ID不一致，请重新核实对应关系。")
    originals = {}
    for identifier in sorted(by_id, key=str):
        user = await owned(db, User, identifier, actor, lock=True)
        if user.status != "deleted" or by_id[identifier].reimported_at is not None:
            raise ApiError(409, "TEACHER_ALREADY_REIMPORTED", "任务内原教师已发生变更，请刷新核对。")
        originals[identifier] = user
    imported, unresolved, versions = [], [], []
    for row in item.rows:
        number = row["row_number"]
        identifier = mapping[number]
        user, snapshot = originals[identifier], by_id[identifier]
        values = {c: row["values"].get(c, "") for c in TEACHER_COLUMNS}
        username = values["教师账号"].strip()
        user.username, user.display_name, user.phone, user.status = username, values["教师姓名"].strip(), values["手机号码"] or None, "active"
        user.account_type = "teacher"
        user.password_hash = await run_in_threadpool(get_password_hash, username)
        user.must_change_password = True
        user.password_version += 1
        # Retain historical grants with their original identity; rebuild current scope.
        grants = (await db.scalars(select(TeachingAssignment).where(
            TeachingAssignment.school_id == actor.school_id, TeachingAssignment.teacher_user_id == identifier,
            TeachingAssignment.status == "active",
        ))).all()
        for grant in grants:
            grant.status = "inactive"
            grant.expires_at = now()
        await db.execute(delete(UserRole).where(UserRole.user_id == identifier, UserRole.school_id == actor.school_id))
        await db.flush()
        duties = duty_codes(values)
        await roster.grant_roles(db, user, duties)
        profile = await db.get(TeacherProfile, identifier)
        if profile:
            profile.fields, profile.duties = values, duties
        else:
            db.add(TeacherProfile(id=identifier, school_id=actor.school_id, fields=values, duties=duties))
        refs = await roster.teacher_grants(db, user, values, duties)
        if refs:
            unresolved.append({"row_number": number, "references": refs})
        snapshot.reimported_user_id, snapshot.reimported_at, snapshot.updated_fields = identifier, now(), values
        changes = [{"field": c, "before": snapshot.fields.get(c, ""), "after": values[c]} for c in TEACHER_COLUMNS if snapshot.fields.get(c, "") != values[c]]
        versions.append({"teacher_id": str(identifier), "platform_id": str(user.platform_id), "row_number": number, "snapshot_id": str(snapshot.id), "changes": changes})
        imported.append({"row_number": number, "id": str(identifier), "platform_id": str(user.platform_id), "account": username})
        audit(db, actor, "roster.teacher.change", user, {"task_id": str(task.id), "snapshot_id": str(snapshot.id), "changes": changes})
    operator = await db.get(User, actor.user_id)
    item.status, item.confirmed_at, item.confirmation = "succeeded", now(), payload
    item.report = {**checked, "success_count": len(imported), "skipped_count": 0, "skipped_rows": [],
                   "imported": imported, "changed_count": len(imported), "unresolved_teaching": unresolved,
                   "versions": versions, "confirmed_by": str(actor.user_id),
                   "confirmed_by_name": operator.display_name or operator.username, "confirmed_at": item.confirmed_at.isoformat()}
    task.status, task.completed_at = "succeeded", item.confirmed_at
    task.confirmation = {"batch_id": str(item.id), "filename": item.filename,
                         "mapping": {str(n): str(i) for n, i in mapping.items()},
                         "confirmed_by": str(actor.user_id), "confirmed_by_name": operator.display_name or operator.username,
                         "versions": versions}
    audit(db, actor, "roster.teacher.task.complete", task, {"batch_id": str(item.id), "success_count": len(imported)})
    await db.commit()
    return roster.view(item)
