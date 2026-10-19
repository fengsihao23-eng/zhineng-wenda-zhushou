"""r86 report maintenance: atomic batches, stable attribution and explicit grants."""
import csv
import hashlib
import io
import unicodedata
from uuid import uuid4
from sqlalchemy import select, delete, update
from sqlalchemy.orm import defer
from app.core.errors import ApiError
from app.db.models import School, User, Student, Exam, Role, UserRole
from app.db.models.exam_management import ExamAdministration, ExamQueryGrant
from app.db.models.report_management import ManagedReport, ReportFile, ReportOperation
from app.services.education_common import owned, data, digest, claim, audit, now
from app.services.curriculum import inspect_file

TYPES = {"student": "个人学情诊断", "classAll": "班级综合诊断", "classSubject": "班级单科诊断",
         "gradeAll": "年级综合诊断", "gradeSubject": "年级单科诊断", "school": "全校学情诊断", "essay": "个人作文批改报告"}
KINDS = {"student": "student", "essay": "student", "classAll": "class", "classSubject": "class",
         "gradeAll": "grade", "gradeSubject": "grade", "school": "school"}
MAX_BATCH_BYTES = 30 * 1024 * 1024


def fail(message, code="REPORT_INVALID", status=422, details=None):
    raise ApiError(status, code, message, details)


def pdf(upload):
    if not upload.filename.lower().endswith(".pdf"):
        fail("请选择非空 PDF 文件。", "REPORT_PDF_REQUIRED")
    content, media_type, pages = inspect_file(upload)
    if media_type != "application/pdf":
        fail("报告仅支持 PDF 文件。")
    # Parsing the page tree alone does not prove that a page can be displayed.
    render_pdf(content, 1)
    return content, len(pages), hashlib.sha256(content).hexdigest()


def render_pdf(content, page):
    import pypdfium2 as pdfium
    try:
        with pdfium.PdfDocument(content) as document:
            if page < 1 or page > len(document):
                fail("PDF 页码超出范围。")
            source = document[page - 1]
            try:
                width, height = source.get_size()
                scale = min(1.6, 1600 / max(width, height))
                bitmap = source.render(scale=scale)
                try:
                    image = bitmap.to_pil()
                    output = io.BytesIO()
                    image.save(output, format="PNG")
                    image.close()
                    return output.getvalue()
                finally:
                    bitmap.close()
            finally:
                source.close()
    except ApiError:
        raise
    except Exception:
        fail("PDF 无法渲染，请选择可正常打开的文件。", "REPORT_PDF_INVALID")


def inspect_pdf(upload):
    content, pages, content_hash = pdf(upload)
    return {"filename": upload.filename, "file_size": len(content), "page_count": pages, "content_hash": content_hash}


def class_key(person):
    return person["grade"] + "|" + person["class_number"]


def classification_errors(config, row):
    errors = []
    if row.category == "essay" and row.report_type != "essay" or row.category == "diagnostic" and row.report_type == "essay":
        errors.append("报告类别与类型不一致")
    subjects = {subject["subject_id"]: subject for subject in config["subjects"]}
    ids = list(map(str, row.subject_ids))
    if len(ids) != 1:
        errors.append("每批只能上传一个科目，请按科目分别上传")
    for sid in ids:
        subject = subjects.get(sid)
        if not subject or not subject["student_ids"]:
            errors.append("科目不在本次考试的有效参试范围内")
        elif row.category == "essay" and subject["name"] not in {"语文", "英语"}:
            errors.append("作文批改报告仅支持本次考试已配置的语文或英语")
    return errors


def targets(config, row):
    ids = list(map(str, row.subject_ids))
    subjects = {s["subject_id"]: s for s in config["subjects"]}
    if not ids or any(sid not in subjects for sid in ids):
        return []
    snap = config["snapshots"]
    rosters = [set(subjects[sid]["student_ids"]) for sid in ids]
    people = sorted(set.union(*rosters))
    kind = KINDS[row.report_type]
    if kind == "student":
        return [{"value": sid, "label": f"{snap[sid]['name']} · {snap[sid]['grade']} {snap[sid]['class_number']} · {snap[sid]['platform_id']}",
                 "detail": "账号 " + snap[sid].get("account", ""), "person": snap[sid]} for sid in people if all(sid in roster for roster in rosters)]
    if kind in {"class", "grade"}:
        group = class_key if kind == "class" else lambda person: person["grade"]
        keys = sorted({group(snap[sid]) for sid in people})
        return [{"value": key, "label": key.replace("|", " "), "detail": "本次考试参试范围"} for key in keys
                if all(any(group(snap[sid]) == key for sid in roster) for roster in rosters)]
    return [{"value": "school", "label": config["school"] + " · 本次考试参试范围", "detail": "本校"}] if all(rosters) else []


def filename_for(exam_code, config, row, target):
    kind = KINDS[row.report_type]
    identity = ([config["snapshots"][target]["platform_id"], config["snapshots"][target]["name"]] if kind == "student"
                else target.split("|") if kind == "class" else ["本校" if kind == "school" else target])
    names = {s["subject_id"]: s["name"] for s in config["subjects"]}
    return "_".join([exam_code, *identity, "+".join(names[str(s)] for s in row.subject_ids), TYPES[row.report_type]]) + ".pdf"


def parse_filename(filename, exam_code, config, row):
    errors = classification_errors(config, row)
    if errors:
        return "", errors
    kind = KINDS[row.report_type]
    parts = filename[:-4].split("_") if filename.lower().endswith(".pdf") else []
    if len(parts) != (5 if kind in {"student", "class"} else 4) or any(not p or p.strip() != p for p in parts):
        return "", ["命名格式不规范；字段须用半角下划线 _ 分隔，请下载本次范围命名清单"]
    if parts[0] != exam_code:
        errors.append("文件名中的考试ID与所选考试不一致")
    if parts[-1] != TYPES[row.report_type]:
        errors.append("文件名中的报告类型与所选类型不一致")
    names = {s["subject_id"]: s["name"] for s in config["subjects"]}
    expected = {names[str(s)] for s in row.subject_ids}
    actual = parts[-2].split("+")
    if len(actual) != len(expected) or set(actual) != expected:
        errors.append("文件名中的科目与所选科目范围不一致")
    candidates = targets(config, row)
    target = ""
    if kind == "student":
        matches = [item for item in candidates if parts[1] in {item["person"]["platform_id"], item["person"].get("account")}]
        if len(matches) != 1:
            errors.append("学生ID或账号不在所选科目的参试名单内或对应多人，请使用唯一学生ID")
        else:
            target = matches[0]["value"]
            if config["snapshots"][target]["name"] != parts[2]:
                errors.append("学生姓名与ID／账号对应的参试学生不一致")
    else:
        target = parts[1] + "|" + parts[2] if kind == "class" else "school" if kind == "school" else parts[1]
        if kind == "school" and parts[1] != "本校":
            errors.append("全校报告的对象字段须填写“本校”")
        if target not in {item["value"] for item in candidates}:
            errors.append("文件名中的对象不在所选科目的参试范围内")
    return target if not errors else "", errors


async def exam_config(db, actor, identifier, revision=None, lock=False):
    admin = await owned(db, ExamAdministration, identifier, actor, lock=lock)
    if revision is not None and admin.revision != revision:
        fail("考试配置或权限已更新，请返回第一步重新核对。", "REPORT_EXAM_CHANGED", 409)
    exam = await owned(db, Exam, identifier, actor)
    return admin, exam


async def options(db, actor):
    school = await db.get(School, actor.school_id)
    rows = (await db.execute(select(Exam, ExamAdministration).join(ExamAdministration, ExamAdministration.id == Exam.id)
                            .where(Exam.school_id == actor.school_id).order_by(Exam.start_date.desc(), Exam.created_at.desc()))).all()
    return {"school": school.name, "exams": [{"id": str(exam.id), "exam_code": exam.external_exam_id or str(exam.id),
            "name": exam.name, "date": admin.configuration["exam_date"], "academic_year": admin.configuration["academic_year"],
            "subject_names": [s["name"] for s in admin.configuration["subjects"]],
            "grades": sorted({p["grade"] for p in admin.configuration["snapshots"].values()}),
            "classes": sorted({class_key(p) for p in admin.configuration["snapshots"].values()})} for exam, admin in rows],
            "types": TYPES, "upload_rule": "single_subject", "max_file_bytes": 15 * 1024 * 1024, "max_batch_bytes": MAX_BATCH_BYTES}


async def exam_options(db, actor, identifier):
    admin, exam = await exam_config(db, actor, identifier)
    teachers = (await db.scalars(select(User).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
                                .where(User.school_id == actor.school_id, UserRole.school_id == actor.school_id, Role.code == "TEACHER")
                                .order_by(User.display_name, User.id))).all()
    return {"id": str(exam.id), "exam_code": exam.external_exam_id or str(exam.id), "revision": admin.revision,
            "school": (await db.get(School, actor.school_id)).name,
            **admin.configuration, "teachers": [{"id": str(t.id), "name": t.display_name or t.username, "account": t.username,
            "platform_id": str(t.platform_id), "login_allowed": t.status == "active" and not t.must_change_password} for t in teachers]}


def attribution(config, exam, row):
    ids = list(map(str, row.subject_ids))
    kind = KINDS[row.report_type]
    snapshots = config["snapshots"]
    coverage = {}
    for subject in config["subjects"]:
        if subject["subject_id"] not in ids:
            continue
        coverage[subject["subject_id"]] = [sid for sid in subject["student_ids"] if
            kind == "student" and sid == row.target_key or kind == "class" and class_key(snapshots[sid]) == row.target_key
            or kind == "grade" and snapshots[sid]["grade"] == row.target_key or kind == "school"]
    people = {sid: snapshots[sid] for students in coverage.values() for sid in students}
    target_label = (snapshots[row.target_key]["name"] + "（" + snapshots[row.target_key]["platform_id"] + "）" if kind == "student"
                    else config["school"] + " · 本次考试参试范围" if kind == "school" else row.target_key.replace("|", " "))
    return {"exam_code": exam.external_exam_id or str(exam.id), "exam_name": exam.name, "school": config["school"],
            "academic_year": config["academic_year"], "category_name": "作文批改报告" if row.category == "essay" else "诊断报告",
            "type_name": TYPES[row.report_type], "subject_names": [s["name"] for s in config["subjects"] if s["subject_id"] in ids],
            "target_label": target_label, "kind": kind, "coverage": coverage, "people": people,
            "grades": sorted({p["grade"] for p in people.values()}), "classes": sorted({class_key(p) for p in people.values()})}


def report_identity(exam_id, row):
    return digest([str(exam_id), row.category, row.report_type, sorted(set(map(str, row.subject_ids))), row.target_key])


async def validate_batch(db, actor, body):
    admin, exam = await exam_config(db, actor, body.exam_id, body.expected_exam_revision, lock=True)
    config = {**admin.configuration, "school": (await db.get(School, actor.school_id)).name}
    errors, checked, seen = [], [], {}
    first_subjects = sorted(map(str, body.reports[0].subject_ids))
    existing = {r.identity_hash: r.report_code for r in (await db.scalars(select(ManagedReport).where(
        ManagedReport.school_id == actor.school_id, ManagedReport.exam_id == body.exam_id, ManagedReport.status == "current"))).all()}
    total_size = 0
    for index, row in enumerate(body.reports):
        problems = classification_errors(config, row)
        if sorted(map(str, row.subject_ids)) != first_subjects or sorted(map(str, row.naming.subject_ids)) != first_subjects:
            problems.append("同一批次的考试和科目必须一致")
        _, naming_errors = parse_filename(row.file.filename, exam.external_exam_id or str(exam.id), config, row.naming)
        problems.extend(naming_errors)
        if row.target_key not in {item["value"] for item in targets(config, row)}:
            problems.append("对象不在所选科目的有效参试范围")
        if not row.previewed:
            problems.append("请逐份预览 PDF 并核对实际内容与归属")
        content, pages, content_hash = b"", 0, ""
        try:
            content, pages, content_hash = pdf(row.file)
            total_size += len(content)
        except ApiError as error:
            problems.append(error.user_message)
        identity = report_identity(body.exam_id, row)
        if identity in seen:
            problems.append(f"与本批第 {seen[identity] + 1} 份报告归属重复")
        seen[identity] = index
        if identity in existing:
            problems.append("与已有报告 " + existing[identity] + " 重复，请使用替换更新")
        if problems:
            errors.append({"filename": row.file.filename, "messages": list(dict.fromkeys(problems))})
        else:
            checked.append({"row": row, "content": content, "page_count": pages, "content_hash": content_hash,
                            "identity_hash": identity, "attribution": attribution(config, exam, row)})
    if total_size > MAX_BATCH_BYTES:
        errors.append({"filename": "本批文件", "messages": ["每批文件合计不能超过 30 MB，请分批上传"]})
    if errors:
        fail("\n".join(item["filename"] + "：" + "；".join(item["messages"]) for item in errors), details={"files": errors})
    checksum = digest([str(body.exam_id), admin.revision, [{"identity": entry["identity_hash"], "content": entry["content_hash"],
                        "filename": entry["row"].file.filename, "attribution": entry["attribution"], "naming": entry["row"].naming.model_dump(mode="json")} for entry in checked]])
    return checked, checksum


async def batch_preview(db, actor, body):
    checked, checksum = await validate_batch(db, actor, body)
    return {"preview_hash": checksum, "count": len(checked), "reports": [{**entry["attribution"], "filename": entry["row"].file.filename,
            "page_count": entry["page_count"], "file_size": len(entry["content"])} for entry in checked]}


async def operator(db, actor):
    user = await owned(db, User, actor.user_id, actor)
    return user.display_name or user.username


def file_meta(file):
    return data(file, "id", "version", "filename", "file_size", "page_count", "content_hash", "reason", "operator_name", "created_at")


def record(report, file):
    return {**data(report, "id", "exam_id", "report_code", "category", "report_type", "subject_ids", "target_key", "version", "status",
                    "operator_name", "created_at", "updated_at"), **report.attribution, "file": file_meta(file)}


async def operation(db, actor, identifier, action, records, reason=""):
    item = ReportOperation(id=identifier, school_id=actor.school_id, action=action, actor_id=actor.user_id,
                           operator_name=await operator(db, actor), reason=reason, details=records)
    db.add(item)
    audit(db, actor, "report-management." + action, item, {"count": len(records)})
    return item


async def replay(db, actor, identifier):
    item = await owned(db, ReportOperation, identifier, actor)
    return {"operation_id": str(item.id), "count": len(item.details), "reports": item.details}


async def batch_save(db, actor, body, key):
    identifier, fresh = await claim(db, actor, "reports.batch", key, body.model_dump(mode="json"))
    if not fresh:
        return await replay(db, actor, identifier)
    checked, checksum = await validate_batch(db, actor, body)
    if not body.preview_hash or body.preview_hash != checksum:
        fail("本批内容已变化，请返回重新预览清单。", "REPORT_PREVIEW_CHANGED", 409)
    stamp, name, records = now(), await operator(db, actor), []
    for entry in checked:
        row, rid = entry["row"], uuid4()
        report = ManagedReport(id=rid, school_id=actor.school_id, exam_id=body.exam_id,
            report_code="RPT-" + stamp.strftime("%Y%m%d") + "-" + rid.hex[:12].upper(), category=row.category,
            report_type=row.report_type, subject_ids=sorted(map(str, row.subject_ids)), target_key=row.target_key,
            identity_hash=entry["identity_hash"], attribution=entry["attribution"], version=1, status="current",
            operator_name=name, created_at=stamp, updated_at=stamp)
        db.add(report)
        await db.flush()
        file = ReportFile(id=uuid4(), school_id=actor.school_id, report_id=rid, version=1, filename=row.file.filename,
            content=entry["content"], file_size=len(entry["content"]), page_count=entry["page_count"], content_hash=entry["content_hash"],
            operator_name=name, reason="", created_at=stamp)
        db.add(file)
        records.append(record(report, file))
    await operation(db, actor, identifier, "上传报告", records)
    await db.commit()
    return await replay(db, actor, identifier)


async def current_report(db, actor, identifier, expected_version=None, lock=False):
    report = await owned(db, ManagedReport, identifier, actor, lock=lock)
    if report.status != "current" or expected_version is not None and report.version != expected_version:
        fail("原报告已变化或删除，请刷新后重新选择。", "REPORT_VERSION_CONFLICT", 409)
    return report


async def current_file(db, actor, report, version=None, include_content=False):
    query = select(ReportFile).where(ReportFile.school_id == actor.school_id, ReportFile.report_id == report.id,
                                    ReportFile.version == (version or report.version))
    file = await db.scalar(query if include_content else query.options(defer(ReportFile.content)))
    if file is None:
        fail("报告文件不存在。", "REPORT_NOT_AVAILABLE", 404)
    return file


async def detail(db, actor, identifier):
    report = await current_report(db, actor, identifier)
    files = (await db.scalars(select(ReportFile).options(defer(ReportFile.content)).where(
        ReportFile.school_id == actor.school_id, ReportFile.report_id == identifier).order_by(ReportFile.version.desc()))).all()
    return {**record(report, files[0]), "versions": [file_meta(file) for file in files]}


async def listing(db, actor, category="", exam_id=None, report_type="", subject="", grade="", cls="", search="", page=1, page_size=12):
    pairs = (await db.execute(select(ManagedReport, ReportFile).options(defer(ReportFile.content)).join(ReportFile,
        (ReportFile.report_id == ManagedReport.id) & (ReportFile.version == ManagedReport.version)).where(
        ManagedReport.school_id == actor.school_id, ReportFile.school_id == actor.school_id, ManagedReport.status == "current")
        .order_by(ManagedReport.updated_at.desc(), ManagedReport.id))).all()
    records = [record(report, file) for report, file in pairs]
    terms = unicodedata.normalize("NFKC", search).casefold().split()
    filtered = [r for r in records if (not category or r["category"] == category) and (not exam_id or r["exam_id"] == str(exam_id))
        and (not report_type or r["report_type"] == report_type) and (not subject or subject in r["subject_names"])
        and (not grade or grade in r["grades"]) and (not cls or cls in r["classes"])
        and all(term in unicodedata.normalize("NFKC", " ".join([r["report_code"], r["file"]["filename"], r["target_label"], r["type_name"], r["exam_name"]])).casefold() for term in terms)]
    facet_records = [r for r in records if not exam_id or r["exam_id"] == str(exam_id)]
    return {"items": filtered[(page - 1) * page_size:page * page_size], "total": len(filtered), "page": page, "page_size": page_size,
        "counts": {"all": len(records), "diagnostic": sum(r["category"] == "diagnostic" for r in records), "essay": sum(r["category"] == "essay" for r in records)},
        "facets": {"subjects": sorted({s for r in facet_records for s in r["subject_names"]}),
                   "grades": sorted({g for r in facet_records for g in r["grades"]}),
                   "classes": sorted({c for r in facet_records for c in r["classes"] if not grade or c.startswith(grade + "|")})}}


async def replace(db, actor, identifier, body, key):
    receipt, fresh = await claim(db, actor, "reports.replace." + str(identifier), key, body.model_dump(mode="json"))
    if not fresh:
        return await replay(db, actor, receipt)
    report = await current_report(db, actor, identifier, body.expected_version, lock=True)
    if not body.confirmed or not body.previewed:
        fail("请预览新 PDF，并确认内容与原报告归属一致。")
    content, pages, content_hash = pdf(body.file)
    old_file = await current_file(db, actor, report)
    previous = record(report, old_file)
    name, stamp = await operator(db, actor), now()
    changed = await db.execute(update(ManagedReport).where(ManagedReport.id == identifier, ManagedReport.school_id == actor.school_id,
        ManagedReport.version == body.expected_version, ManagedReport.status == "current").values(
        version=body.expected_version + 1, operator_name=name, updated_at=stamp).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        fail("原报告已变化，请刷新后重新打开替换。", "REPORT_VERSION_CONFLICT", 409)
    await db.refresh(report)
    file = ReportFile(id=uuid4(), school_id=actor.school_id, report_id=identifier, version=report.version, filename=body.file.filename,
        content=content, file_size=len(content), page_count=pages, content_hash=content_hash, reason=body.reason, operator_name=name, created_at=stamp)
    db.add(file)
    await operation(db, actor, receipt, "替换更新", [{**record(report, file), "previous_file": previous["file"]}], body.reason)
    await db.commit()
    return await replay(db, actor, receipt)


async def remove(db, actor, body, key):
    receipt, fresh = await claim(db, actor, "reports.delete", key, body.model_dump(mode="json"))
    if not fresh:
        return await replay(db, actor, receipt)
    if not body.confirmed:
        fail("请核对清单并确认删除所选报告。")
    if len({item.id for item in body.reports}) != len(body.reports):
        fail("删除清单不能包含重复报告。")
    records = []
    for item in body.reports:
        report = await current_report(db, actor, item.id, item.expected_version, lock=True)
        records.append(record(report, await current_file(db, actor, report)))
    for item in body.reports:
        changed = await db.execute(update(ManagedReport).where(ManagedReport.id == item.id, ManagedReport.school_id == actor.school_id,
            ManagedReport.version == item.expected_version, ManagedReport.status == "current").values(status="deleted", updated_at=now())
            .execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            fail("报告状态已变化，请刷新后重新核对删除清单。", "REPORT_VERSION_CONFLICT", 409)
        # Remove every retrievable PDF version; the operation preserves metadata.
        await db.execute(delete(ReportFile).where(ReportFile.school_id == actor.school_id, ReportFile.report_id == item.id))
    await operation(db, actor, receipt, "删除报告", records, body.reason)
    await db.commit()
    return await replay(db, actor, receipt)


async def logs(db, actor, page=1, page_size=12):
    from sqlalchemy import func
    conditions = [ReportOperation.school_id == actor.school_id]
    total = await db.scalar(select(func.count()).select_from(ReportOperation).where(*conditions))
    rows = (await db.scalars(select(ReportOperation).where(*conditions).order_by(ReportOperation.created_at.desc(), ReportOperation.id)
                            .offset((page - 1) * page_size).limit(page_size))).all()
    return {"total": total, "items": [data(row, "id", "action", "operator_name", "reason", "details", "created_at") for row in rows]}


def access_decision(report, kind, recipient, granted, login_allowed=True):
    if not login_allowed:
        return False, "账号不可登录"
    if report.status != "current":
        return False, "报告已删除或文件不可用"
    attr = report.attribution
    if kind == "student":
        if attr["kind"] != "student" or report.target_key != str(recipient):
            return False, "仅可查看本人个人报告"
        content = "student"
    elif kind == "teacher":
        content = "essay:" + ("chinese" if attr["subject_names"] == ["语文"] else "english") if report.category == "essay" else "diagnosis:" + report.report_type
        if not any(value[2] == content for value in granted):
            return False, "未获此类报告的查询授权"
    else:
        return False, "查询身份无效"
    required = {(sid, sub, content) for sub, students in attr["coverage"].items() for sid in students}
    if not required or not required <= granted:
        return False, "报告所需科目或完整对象范围未获授权"
    return True, "本人报告，所需科目已开放" if kind == "student" else "类型、科目及完整对象范围已获准"


async def grants(db, actor, exam_id, kind, recipient):
    rows = (await db.scalars(select(ExamQueryGrant).where(ExamQueryGrant.school_id == actor.school_id,
        ExamQueryGrant.exam_id == exam_id, ExamQueryGrant.recipient_kind == kind, ExamQueryGrant.recipient_id == recipient))).all()
    return {(str(g.student_id), str(g.subject_id), g.content_type) for g in rows}


async def access_check(db, actor, exam_id, kind, recipient, login=True):
    admin, _ = await exam_config(db, actor, exam_id)
    if kind == "student":
        if str(recipient) not in admin.configuration["snapshots"]:
            fail("请选择本次考试参试学生。")
        student = await owned(db, Student, recipient, actor)
        user = await owned(db, User, student.user_id, actor) if student.user_id else None
    else:
        user = await owned(db, User, recipient, actor)
        teacher_role = await db.scalar(select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(
            UserRole.school_id == actor.school_id, UserRole.user_id == recipient, Role.code == "TEACHER"))
        if not teacher_role:
            fail("请选择本校教师账号。")
    login_allowed = login and user is not None and user.status == "active" and not user.must_change_password
    approved = await grants(db, actor, exam_id, kind, recipient)
    reports = (await db.scalars(select(ManagedReport).where(ManagedReport.school_id == actor.school_id,
        ManagedReport.exam_id == exam_id, ManagedReport.status == "current").order_by(ManagedReport.created_at.desc()))).all()
    return {"reports": [{"id": str(r.id), "report_code": r.report_code, **r.attribution,
             "allowed": access_decision(r, kind, recipient, approved, login_allowed)[0],
             "why": access_decision(r, kind, recipient, approved, login_allowed)[1]}
             for r in reports if kind != "student" or r.attribution["kind"] == "student" and r.target_key == str(recipient)]}


async def authorized_reports(db, actor, exam_id, kind, recipient, view_type="student"):
    approved = await grants(db, actor, exam_id, kind, recipient)
    reports = (await db.scalars(select(ManagedReport).where(ManagedReport.school_id == actor.school_id,
        ManagedReport.exam_id == exam_id, ManagedReport.status == "current").order_by(ManagedReport.updated_at.desc()))).all()
    return [r for r in reports if (kind == "student" or r.category == "essay" or r.report_type == view_type)
            and access_decision(r, kind, recipient, approved)[0]]


async def recipient_file(db, actor, exam_id, identifier, kind, recipient, view_type):
    reports = await authorized_reports(db, actor, exam_id, kind, recipient, view_type)
    report = next((r for r in reports if r.id == identifier), None)
    if report is None:
        fail("报告不存在或不在本次考试授权范围内。", "REPORT_NOT_AVAILABLE", 404)
    return report, await current_file(db, actor, report, include_content=True)


def naming_csv(exam_code, config, classification):
    errors = classification_errors(config, classification)
    if errors:
        fail("；".join(errors))
    output = io.StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(["报告对象", "建议文件名"])
    for item in targets(config, classification):
        values = [item["label"], filename_for(exam_code, config, classification, item["value"])]
        writer.writerow(["'" + v if v.startswith(("=", "+", "-", "@")) else v for v in values])
    return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")
