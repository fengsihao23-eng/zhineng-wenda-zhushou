"""Preview and remove only selected students' personal data; refresh involved exams."""
from collections import defaultdict
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select, or_, func, delete, update
from app.core.errors import ApiError
from app.db.base import Base
from app.db.models import (Student, User, UserRole, StudentExamScore, StudentSubjectScore,
                           QuestionScore, DiagnosisReport, Exam, StudentExamPlacement)
from app.services import student_roster as roster
from app.services.education_common import now

LABELS = {"student_exam_scores": "考试总分", "student_subject_scores": "科目成绩", "question_scores": "小题成绩",
          "diagnosis_reports": "学情报告", "education_reviews": "错题", "education_review_records": "错题复习",
          "chat_sessions": "问答会话", "chat_messages": "问答消息", "agent_runs": "问答分析",
          "tool_call_logs": "问答工具记录", "model_usage_logs": "模型用量", "student_entitlements": "个人权益",
          "parent_authorizations": "家长授权", "student_year_classes": "学年班级记录",
          "student_exam_placements": "历史考试班级归属", "education_report_attachments": "报告附件",
          "education_assets": "个人报告文件", "platform_feedback": "个人反馈", "risk_events": "个人风险记录",
          "human_handoffs": "人工接管", "education_handoff_messages": "接管消息", "user_roles": "账号权限"}


async def deletion_plan(db, actor, students):
    ids = [s.id for s in students]
    users = [s.user_id for s in students if s.user_id]
    tables = list(Base.metadata.sorted_tables)
    targets = {}
    for table in tables:
        if "student_id" in table.c and any(fk.column.table.name == "students" for fk in table.c.student_id.foreign_keys):
            predicate = table.c.student_id.in_(ids)
            targets[table.name] = predicate & (table.c.school_id == actor.school_id) if "school_id" in table.c else predicate
    targets["user_roles"] = UserRole.user_id.in_(users) & (UserRole.school_id == actor.school_id)
    if "platform_feedback" in Base.metadata.tables:
        table = Base.metadata.tables["platform_feedback"]
        targets[table.name] = or_(targets.get(table.name, False), (table.c.user_id.in_(users) & (table.c.school_id == actor.school_id)))
    # Build descendants from actual foreign keys. Shared exams, classes, source
    # batches and questions are parents and never enter this removal graph.
    for table in tables:
        parts = [targets[table.name]] if table.name in targets else []
        for column in table.c:
            for fk in column.foreign_keys:
                parent = fk.column.table
                if fk.column.name == "id" and parent.name in targets:
                    parts.append(column.in_(select(parent.c.id).where(targets[parent.name])))
        if parts:
            predicate = or_(*parts)
            targets[table.name] = predicate & (table.c.school_id == actor.school_id) if "school_id" in table.c else predicate
    # Remove a report blob only when no retained attachment/paper still uses it.
    attachment = Base.metadata.tables["education_report_attachments"]
    assets = Base.metadata.tables["education_assets"]
    if attachment.name in targets:
        selected_assets = (await db.scalars(select(attachment.c.asset_id).where(targets[attachment.name]))).all()
        exclusive = []
        for aid in set(selected_assets):
            shared = False
            for table in tables:
                for column in table.c:
                    if any(fk.column.table.name == assets.name and fk.column.name == "id" for fk in column.foreign_keys):
                        condition = column == aid
                        if table.name in targets:
                            condition &= ~targets[table.name]
                        if await db.scalar(select(func.count()).select_from(table).where(condition)):
                            shared = True
            if not shared:
                exclusive.append(aid)
        targets[assets.name] = assets.c.id.in_(exclusive) & (assets.c.school_id == actor.school_id)
    detach, barriers = [], []
    for table in tables:
        if table.name == "students":
            continue
        for column in table.c:
            if not any(fk.column.table.name == "users" and fk.column.name == "id" for fk in column.foreign_keys):
                continue
            condition = column.in_(users)
            if table.name in targets:
                condition &= ~targets[table.name]
            if "school_id" in table.c:
                condition &= table.c.school_id == actor.school_id
            count = await db.scalar(select(func.count()).select_from(table).where(condition))
            if count:
                if column.nullable:
                    detach.append((table, column, condition))
                else:
                    barriers.append(table.name)
    return targets, detach, sorted(set(barriers))


async def affected_exams(db, actor, ids):
    result = set()
    for model in (StudentExamScore, StudentSubjectScore, QuestionScore, DiagnosisReport):
        result.update((await db.scalars(select(model.exam_id).where(model.school_id == actor.school_id, model.student_id.in_(ids)))).all())
    result.discard(None)
    return result


async def deletion_preview(db, actor, students):
    targets, _, barriers = await deletion_plan(db, actor, students)
    totals = []
    for name, condition in targets.items():
        count = await db.scalar(select(func.count()).select_from(Base.metadata.tables[name]).where(condition))
        if count:
            totals.append({"type": name, "label": LABELS.get(name, name), "count": count})
    exams = await affected_exams(db, actor, [s.id for s in students])
    exam_rows = (await db.scalars(select(Exam).where(Exam.school_id == actor.school_id, Exam.id.in_(exams)))).all()
    placements = {(p.student_id, p.exam_id): p for p in (await db.scalars(select(StudentExamPlacement).where(
        StudentExamPlacement.school_id == actor.school_id, StudentExamPlacement.student_id.in_([s.id for s in students]),
        StudentExamPlacement.exam_id.in_(exams)))).all()}
    school, classes = await roster.school(db, actor.school_id), await roster.class_map(db, actor.school_id)
    projected = {s.id: roster.fields31(s, u, school, classes) for s, u in await roster.people(db, actor.school_id, [s.id for s in students])}
    participation = defaultdict(set)
    for model in (StudentExamScore, StudentSubjectScore, QuestionScore, DiagnosisReport):
        for sid, eid in (await db.execute(select(model.student_id, model.exam_id).where(
            model.school_id == actor.school_id, model.student_id.in_(projected), model.exam_id.in_(exams)))).all():
            participation[sid].add(eid)
    locations = {}
    for e in exam_rows:
        grades, class_labels = set(), set()
        for student in students:
            if e.id not in participation[student.id]:
                continue
            placement = placements.get((student.id, e.id))
            fields = projected[student.id]
            grade = placement.grade if placement else fields["年级（1-12）"]
            number = placement.class_number if placement else fields["班级号"]
            grades.add(grade or "未登记年级")
            class_labels.add(grade + number or "未登记班级")
        locations[e.id] = {"grades": sorted(grades), "classes": sorted(class_labels)}
    return {"affected": totals, "affected_exams": [{"id": str(e.id), "name": e.name, "academic_year": e.academic_year,
                                                    **locations[e.id], "scope": "对应班级、年级及全校汇总/排名、相关报告统计；无关班级年级的已有统计保留"} for e in exam_rows],
            "deletion_barriers": barriers}


async def delete_student_data(db, actor, students, preview):
    targets, detach, barriers = await deletion_plan(db, actor, students)
    if barriers:
        raise ApiError(409, "SHARED_USER_RECORDS", "原账号还参与共享业务记录，请先移交后办理，避免删除其他学生或共享资料。", details={"references": barriers})
    exams = await affected_exams(db, actor, [s.id for s in students])
    # Freeze all involved participants before deletion, so rankings use the
    # exam's original class/grade even after subsequent promotion.
    participants = set()
    for model in (StudentExamScore, StudentSubjectScore, QuestionScore, DiagnosisReport):
        participants.update((await db.scalars(select(model.student_id).where(model.school_id == actor.school_id, model.exam_id.in_(exams)))).all())
    school, classes = await roster.school(db, actor.school_id), await roster.class_map(db, actor.school_id)
    for student, user in await roster.people(db, actor.school_id, participants):
        await roster.freeze_history(db, student, roster.fields31(student, user, school, classes), roster.current_year(school), exams)
    placements = {(p.student_id, p.exam_id): p for p in (await db.scalars(select(StudentExamPlacement).where(
        StudentExamPlacement.school_id == actor.school_id, StudentExamPlacement.exam_id.in_(exams)))).all()}
    impacted_classes, impacted_grades = set(), set()
    for model in (StudentExamScore, StudentSubjectScore):
        for score in (await db.scalars(select(model).where(model.school_id == actor.school_id,
            model.student_id.in_([s.id for s in students]), model.exam_id.in_(exams)))).all():
            grade, class_key = location(placements.get((score.student_id, score.exam_id)))
            subject = getattr(score, "subject_id", None)
            impacted_grades.add((score.exam_id, subject, grade))
            impacted_classes.add((score.exam_id, subject, grade, class_key))
    targets, detach, _ = await deletion_plan(db, actor, students)
    counts = {}
    for name, condition in targets.items():
        counts[name] = int(await db.scalar(select(func.count()).select_from(Base.metadata.tables[name]).where(condition)) or 0)
    # Materialise IDs while all parents exist; evaluating nested subqueries after
    # removing a parent could otherwise leave orphaned descendants behind.
    selected = {name: list((await db.scalars(select(Base.metadata.tables[name].c.id).where(condition))).all())
                for name, condition in targets.items() if "id" in Base.metadata.tables[name].c}
    for table, column, condition in detach:
        await db.execute(update(table).where(condition).values({column.name: None}))
    for table in reversed(Base.metadata.sorted_tables):
        if table.name not in targets:
            continue
        condition = table.c.id.in_(selected[table.name]) if table.name in selected else targets[table.name]
        await db.execute(delete(table).where(condition))
    ids, users = [s.id for s in students], [s.user_id for s in students if s.user_id]
    await db.execute(delete(Student).where(Student.school_id == actor.school_id, Student.id.in_(ids)))
    if users:
        await db.execute(delete(User).where(User.school_id == actor.school_id, User.id.in_(users)))
    await db.flush()
    reports = await recalculate(db, actor, exams, impacted_classes, impacted_grades)
    return {"deleted_students": len(ids), "deleted_accounts": len(users), "personal_data_counts": counts,
            "recalculated_exam_ids": sorted(str(e) for e in exams), "refreshed_report_statistics": reports,
            "snapshot_retained": True, "account_released": True}


def ranks(rows, attribute):
    ordered = sorted(rows, key=lambda row: getattr(row, attribute), reverse=True)
    rank = 0
    previous = None
    values = {}
    for position, row in enumerate(ordered, 1):
        value = getattr(row, attribute)
        if previous is None or value != previous:
            rank = position
        previous = value
        values[row.id] = rank
    return values


def location(placement):
    if placement is None:
        return "", ""
    grade = roster.grade_rank(placement.grade) or placement.grade
    return grade, placement.class_number or str(placement.class_id or placement.external_class_id or "")


async def recalculate(db, actor, exams, impacted_classes, impacted_grades):
    if not exams:
        return 0
    placements = {(r.student_id, r.exam_id): r for r in (await db.scalars(select(StudentExamPlacement).where(
        StudentExamPlacement.school_id == actor.school_id, StudentExamPlacement.exam_id.in_(exams)))).all()}
    refreshed = {}
    for model, score_field in ((StudentExamScore, "total_score"), (StudentSubjectScore, "score")):
        rows = (await db.scalars(select(model).where(model.school_id == actor.school_id, model.exam_id.in_(exams)).with_for_update())).all()
        class_groups, grade_groups = defaultdict(list), defaultdict(list)
        for row in rows:
            p = placements.get((row.student_id, row.exam_id))
            subject = getattr(row, "subject_id", None)
            grade, class_key = location(p)
            class_groups[(row.exam_id, subject, grade, class_key)].append(row)
            grade_groups[(row.exam_id, subject, grade)].append(row)
        for groups, kind in ((class_groups, "class"), (grade_groups, "grade")):
            for key, group in groups.items():
                if key not in (impacted_classes if kind == "class" else impacted_grades):
                    continue
                values = ranks(group, score_field)
                average = sum(Decimal(getattr(row, score_field)) for row in group) / len(group)
                for row in group:
                    setattr(row, kind + "_rank", values[row.id])
                    if model is StudentExamScore:
                        setattr(row, kind + "_student_count", len(group))
                    else:
                        setattr(row, kind + "_avg", average.quantize(Decimal("0.01")))
        for row in rows:
            grade, class_key = location(placements.get((row.student_id, row.exam_id)))
            subject = getattr(row, "subject_id", None)
            if (row.exam_id, subject, grade) not in impacted_grades and (row.exam_id, subject, grade, class_key) not in impacted_classes:
                continue
            refreshed[(row.student_id, row.exam_id, getattr(row, "subject_id", None))] = {
                "class_rank": row.class_rank, "grade_rank": row.grade_rank,
                **({"class_student_count": row.class_student_count, "grade_student_count": row.grade_student_count}
                   if model is StudentExamScore else {"class_avg": float(row.class_avg) if row.class_avg is not None else None,
                                                      "grade_avg": float(row.grade_avg) if row.grade_avg is not None else None})}
    reports = (await db.scalars(select(DiagnosisReport).where(DiagnosisReport.school_id == actor.school_id,
                                                           DiagnosisReport.exam_id.in_(exams)))).all()
    changed = 0
    for report in reports:
        statistics = refreshed.get((report.student_id, report.exam_id, report.subject_id))
        if statistics:
            # Keep the imported original report and its attachment immutable;
            # publish authoritative recalculated statistics as a separate overlay.
            report.structured_json = {**report.structured_json, "recalculated_statistics": statistics,
                                       "statistics_recalculated_at": now().isoformat()}
            changed += 1
    await db.flush()
    return changed
