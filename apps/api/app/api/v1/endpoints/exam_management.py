"""School-scoped exam administration and permission-filtered result reads."""
from typing import Literal
from uuid import UUID
from urllib.parse import quote
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.errors import ApiError
from app.db.models import School, Student, StudentSubjectScore, StudentExamScore, QuestionScore, DiagnosisReport
from app.db.models.education import ReportAttachment, PrivateAsset
from app.db.models.exam_management import ExamQueryPolicy, ExamQueryGrant
from app.api.v1.endpoints.education import exam_read_role as base_exam_reader, exam_write_role, write
from app.schemas.exam_management import (ExamDraft, ScoreUpload, Revision, TeacherPermissions, StudentPermissions, Upload)
from app.services import exam_management as service
from app.services import report_management as report_service
from app.services.education_common import data, audit

router = APIRouter(prefix="/platform/education/exam-management", tags=["exam-management"])


async def exam_read_role(actor=Depends(base_exam_reader)):
    if actor.has_role("TEACHER") and not any(actor.has_role(r) for r in ["SCHOOL_ADMIN", "SUPER_ADMIN", "QA", "EXAM_ADMIN"]):
        raise ApiError(403, "EXAM_ADMIN_REQUIRED", "请通过“考试成绩与报告”查询管理员为你授权的考试数据。")
    return actor


async def writer(actor=Depends(exam_write_role), db: AsyncSession = Depends(get_db)):
    await db.scalar(select(School.id).where(School.id == actor.school_id).with_for_update())
    return actor


def excel(content, filename, checksum=None):
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''"+quote(filename),
                 **({"X-Exam-Preview-Hash": checksum} if checksum else {})})


@router.get("/options")
async def options(academic_year: str | None = Query(None, max_length=20), actor=Depends(exam_read_role), db: AsyncSession = Depends(get_db)):
    return await service.options(db, actor, academic_year)


@router.get("/teachers")
async def teachers(exam_id: UUID | None = None, actor=Depends(exam_read_role), db: AsyncSession = Depends(get_db)):
    return await service.teacher_permission_options(db, actor, exam_id) if exam_id else await service.teacher_options(db, actor)


@router.get("/teacher-default-rules")
async def teacher_default_rules(actor=Depends(exam_read_role)):
    return excel(service.teacher_default_rules_file(), "教师默认选项规则.xlsx")


@router.get("/operations")
async def operations(exam_id: UUID | None = None, category: Literal["", "exam", "permission"] = "", page: int = Query(1, ge=1),
                     page_size: int = Query(20, ge=1, le=100), actor=Depends(exam_read_role), db: AsyncSession = Depends(get_db)):
    return await service.logs(db, actor, exam_id, category, page, page_size)


@router.get("")
async def listing(search: str = Query("", max_length=200), academic_year: str = Query("", max_length=20),
                  state: Literal["", "none", "part", "open"] = "", grade: str = Query("", max_length=100),
                  subject: str = Query("", max_length=100), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                  actor=Depends(exam_read_role), db: AsyncSession = Depends(get_db)):
    return await service.listing(db, actor, search, academic_year, state, grade, subject, page, page_size)


@router.post("/preview")
async def preview(body: ExamDraft, actor=Depends(exam_write_role), db: AsyncSession = Depends(get_db)):
    return await service.preview(db, actor, body)


@router.post("")
async def create(body: ExamDraft, key: UUID | None = Header(None, alias="Idempotency-Key"),
                 actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, service.save(db, actor, body, key))


@router.get("/my-exams")
async def my_exams(actor=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    kind, recipient = await recipient_for(db, actor)
    policies = (await db.scalars(select(ExamQueryPolicy).where(ExamQueryPolicy.school_id == actor.school_id,
        ExamQueryPolicy.recipient_kind == kind, ExamQueryPolicy.recipient_id == recipient))).all()
    result = []
    for policy in policies:
        if kind == "student" and not policy.configuration.get("subjects"):
            continue
        from app.db.models import Exam
        exam = await db.get(Exam, policy.exam_id)
        result.append({"id": str(exam.id), "name": exam.name, "exam_id": exam.external_exam_id,
                       "date": exam.start_date.isoformat() if exam.start_date else None, "permissions": policy.configuration})
    return result


async def recipient_for(db, actor):
    if actor.has_role("STUDENT"):
        student = await db.scalar(select(Student).where(Student.school_id == actor.school_id, Student.user_id == actor.user_id, Student.status == "active"))
        if student:
            from app.core.exam_access import bind_student
            bind_student(db, actor.school_id, student.id)
            return "student", student.id
    if actor.has_role("TEACHER"):
        from app.core.exam_access import bind_teacher
        bind_teacher(db, actor.school_id, actor.user_id)
        return "teacher", actor.user_id
    raise ApiError(403, "EXAM_RECIPIENT_REQUIRED", "此入口仅供已获考试查询授权的教师或学生使用。")


@router.get("/my-exams/{identifier}")
async def my_results(identifier: UUID, view_type: Literal["student", "classSubject", "gradeSubject", "classAll", "gradeAll", "school"] = "student",
                     actor=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    kind, recipient = await recipient_for(db, actor)
    grant_rows = (await db.scalars(select(ExamQueryGrant).where(ExamQueryGrant.school_id == actor.school_id,
        ExamQueryGrant.exam_id == identifier, ExamQueryGrant.recipient_kind == kind, ExamQueryGrant.recipient_id == recipient))).all()
    if not grant_rows:
        raise ApiError(404, "EXAM_NOT_AVAILABLE", "本次考试尚未向你开放查询。")
    granted = {(g.student_id, g.subject_id, g.content_type) for g in grant_rows}
    allowed = {(sid, sub) for sid, sub, content in granted if content == ("student" if kind == "student" else "score:"+view_type)}
    detail = await service.detail(db, actor, identifier)
    subjects = {s["subject_id"]: s["name"] for s in detail["subjects"]}
    scores = (await db.scalars(select(StudentSubjectScore).where(StudentSubjectScore.school_id == actor.school_id,
        StudentSubjectScore.exam_id == identifier).execution_options(exam_view_type=view_type))).all()
    questions = (await db.scalars(select(QuestionScore).where(QuestionScore.school_id == actor.school_id,
        QuestionScore.exam_id == identifier).execution_options(exam_view_type=view_type))).all()
    reports = (await db.scalars(select(DiagnosisReport).where(DiagnosisReport.school_id == actor.school_id,
        DiagnosisReport.exam_id == identifier, DiagnosisReport.status == "generated").execution_options(exam_view_type=view_type))).all()
    def score_view(row):
        snap = detail["snapshots"].get(str(row.student_id), {})
        return {"student_id": snap.get("platform_id"), "student_name": snap.get("name", ""), "grade": snap.get("grade", ""),
                "class_number": snap.get("class_number", ""), "subject": subjects.get(str(row.subject_id), "历史科目"),
                **data(row, "score", "full_score", "class_rank", "grade_rank"),
                "questions": [{"question_no": q.question_no, "score": float(q.score)} for q in questions
                              if q.student_id == row.student_id and q.subject_id == row.subject_id]}
    def report_allowed(report):
        if kind == "student":
            if report.student_id != recipient:
                return False
            if report.subject_id:
                return (report.student_id, report.subject_id, "student") in granted
            required = {(s.student_id, s.subject_id) for s in scores if s.student_id == recipient}
            return bool(required) and required <= allowed
        content = "essay:"+("chinese" if subjects.get(str(report.subject_id)) == "语文" else "english") if report.report_type in {"essay", "essay_report", "marked_work"} else "diagnosis:"+view_type
        report_scope = (report.structured_json or {}).get("scope_type", "student")
        if report.subject_id is None:
            required = {(report.student_id, UUID(s["subject_id"])) for s in detail["subjects"] if str(report.student_id) in s["student_ids"]}
            approved = {(sid, sub) for sid, sub, kind in granted if kind == "diagnosis:"+view_type}
            return report_scope == view_type and bool(required) and required <= approved
        return (content.startswith("essay:") or report_scope == view_type) and (report.student_id, report.subject_id, content) in granted
    total_rows = (await db.scalars(select(StudentExamScore).where(StudentExamScore.school_id == actor.school_id,
        StudentExamScore.exam_id == identifier).execution_options(exam_view_type=view_type))).all()
    totals = []
    for total in total_rows:
        required = {(s.student_id, s.subject_id) for s in scores if s.student_id == total.student_id}
        if required and required <= allowed and (kind == "student" or view_type in {"classAll", "gradeAll", "school"}):
            snap = detail["snapshots"].get(str(total.student_id), {})
            totals.append({"student_id": snap.get("platform_id"), "student_name": snap.get("name", ""),
                           "grade": snap.get("grade", ""), "class_number": snap.get("class_number", ""),
                           **data(total, "total_score", "full_score", "class_rank", "grade_rank")})
    from app.db.models import Subject
    historical_subjects = (await db.scalars(select(Subject).where(Subject.school_id == actor.school_id,
        Subject.id.in_([s.subject_id for s in scores])))).all()
    for subject in historical_subjects:
        subjects.setdefault(str(subject.id), subject.name)
    maintained = await report_service.authorized_reports(db, actor, identifier, kind, recipient, view_type)
    maintained_views = []
    for report in maintained:
        file = await report_service.current_file(db, actor, report)
        maintained_views.append({**data(report, "id", "report_type", "version"),
            "generated_at": report.updated_at.isoformat(), "type_name": report.attribution["type_name"],
            "target_label": report.attribution["target_label"], "subject_names": report.attribution["subject_names"],
            "filename": file.filename, "page_count": file.page_count, "managed": True})
    return {"id": detail["id"], "name": detail["name"], "exam_id": detail["exam_id"], "kind": kind,
            "scores": [score_view(row) for row in scores if (row.student_id, row.subject_id) in allowed],
            "totals": totals,
            "reports": [data(r, "id", "subject_id", "report_type", "version", "generated_at") for r in reports if report_allowed(r)] + maintained_views}


@router.get("/my-exams/{identifier}/reports/{report_id}/original")
async def my_report_original(identifier: UUID, report_id: UUID,
    view_type: Literal["student", "classSubject", "gradeSubject", "classAll", "gradeAll", "school"] = "student",
    page: int | None = Query(None, ge=1, le=100),
    actor=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await my_results(identifier, view_type, actor, db)
    if str(report_id) not in {r["id"] for r in result["reports"]}:
        raise ApiError(404, "REPORT_NOT_AVAILABLE", "报告不存在或不在本次考试授权范围内。")
    if any(r["id"] == str(report_id) and r.get("managed") for r in result["reports"]):
        kind, recipient = await recipient_for(db, actor)
        report, file = await report_service.recipient_file(db, actor, identifier, report_id, kind, recipient, view_type)
        content = report_service.render_pdf(file.content, page) if page else file.content
        audit(db, actor, "exam.report.read", report, {"version": report.version, "page": page})
        await db.commit()
        from app.api.v1.endpoints.report_management import private_response
        return private_response(content, "image/png" if page else "application/pdf", None if page else file.filename)
    asset = await db.scalar(select(PrivateAsset).join(ReportAttachment, ReportAttachment.asset_id == PrivateAsset.id).where(
        ReportAttachment.school_id == actor.school_id, ReportAttachment.report_id == report_id, PrivateAsset.school_id == actor.school_id))
    if asset is None:
        raise ApiError(404, "REPORT_SOURCE_MISSING", "该报告尚未上传 PDF 原件。")
    audit(db, actor, "exam.report.read", asset, {"exam_id": str(identifier), "report_id": str(report_id)})
    await db.commit()
    return Response(asset.content, media_type=asset.media_type, headers={"Content-Disposition": "attachment; filename*=UTF-8''"+quote(asset.filename)})


@router.get("/{identifier}")
async def detail(identifier: UUID, actor=Depends(exam_read_role), db: AsyncSession = Depends(get_db)):
    return await service.detail(db, actor, identifier)


@router.post("/{identifier}/preview")
async def adjustment_preview(identifier: UUID, body: ExamDraft, actor=Depends(exam_write_role), db: AsyncSession = Depends(get_db)):
    return await service.preview(db, actor, body, identifier)


@router.put("/{identifier}")
async def adjust(identifier: UUID, body: ExamDraft, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, service.save(db, actor, body, identifier=identifier))


@router.post("/{identifier}/roster-preview")
async def roster_preview(identifier: UUID, body: ExamDraft, actor=Depends(exam_read_role), db: AsyncSession = Depends(get_db)):
    checked = await service.preview(db, actor, body, identifier)
    return roster_excel(checked["configuration"])


def roster_excel(config):
    rows = [[config["academic_year"], config["snapshots"][sid]["grade"], config["snapshots"][sid]["class_number"],
        config["snapshots"][sid]["platform_id"], config["snapshots"][sid]["name"], config["snapshots"][sid]["account"], s["name"]]
        for s in config["subjects"] for sid in s["student_ids"]]
    return excel(service.workbook_bytes(["考试学年", "年级", "班级", "学生ID", "学生姓名", "学生账号", "科目"], rows), "参试名单.xlsx")


@router.post("/preview/roster")
async def create_roster_preview(body: ExamDraft, actor=Depends(exam_write_role), db: AsyncSession = Depends(get_db)):
    return roster_excel((await service.preview(db, actor, body))["configuration"])


@router.get("/{identifier}/score-template/{subject_id}")
async def score_template(identifier: UUID, subject_id: UUID, actor=Depends(exam_read_role), db: AsyncSession = Depends(get_db)):
    return excel(await service.score_template(db, actor, identifier, subject_id), "成绩模板.xlsx")


@router.post("/{identifier}/score-files")
async def score_preflight(identifier: UUID, body: ScoreUpload, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, service.score_preflight(db, actor, identifier, body))


@router.post("/{identifier}/score-files/{file_id}/confirm")
async def score_confirm(identifier: UUID, file_id: UUID, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, service.score_confirm(db, actor, identifier, file_id))


@router.get("/{identifier}/score-files/{file_id}/original")
async def score_original(identifier: UUID, file_id: UUID, actor=Depends(exam_read_role), db: AsyncSession = Depends(get_db)):
    file = await service.score_file(db, actor, identifier, file_id)
    return Response(file.original_content, media_type="application/octet-stream", headers={"Content-Disposition": "attachment; filename*=UTF-8''"+quote(file.filename)})


@router.post("/{identifier}/score-files/{subject_id}/delete")
async def score_delete(identifier: UUID, subject_id: UUID, body: Revision, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, service.score_delete(db, actor, identifier, subject_id, body))


async def permission_excel(db, actor, identifier, body, kind):
    checked = await service.permission_preview(db, actor, identifier, body, kind)
    return excel(service.workbook_bytes(checked["headers"], checked["rows"]), ("教师" if kind == "teacher" else "学生")+"授权预览.xlsx", checked["preview_hash"])


@router.post("/{identifier}/permissions/teacher/preview")
async def teacher_preview(identifier: UUID, body: TeacherPermissions, actor=Depends(exam_write_role), db: AsyncSession = Depends(get_db)):
    return await permission_excel(db, actor, identifier, body, "teacher")


@router.post("/{identifier}/permissions/student/preview")
async def student_preview(identifier: UUID, body: StudentPermissions, actor=Depends(exam_write_role), db: AsyncSession = Depends(get_db)):
    return await permission_excel(db, actor, identifier, body, "student")


@router.post("/{identifier}/permissions/teacher")
async def teacher_save(identifier: UUID, body: TeacherPermissions, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, service.permission_save(db, actor, identifier, body, "teacher"))


@router.post("/{identifier}/permissions/student")
async def student_save(identifier: UUID, body: StudentPermissions, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, service.permission_save(db, actor, identifier, body, "student"))


@router.post("/{identifier}/permissions/teacher/{teacher_id}/revoke")
async def teacher_revoke(identifier: UUID, teacher_id: UUID, body: Revision, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, service.revoke_teacher(db, actor, identifier, teacher_id, body))


@router.post("/{identifier}/permissions/{kind}/upload")
async def permission_upload(identifier: UUID, kind: Literal["teacher", "student"], body: Upload,
                            actor=Depends(exam_write_role), db: AsyncSession = Depends(get_db)):
    return await service.permission_upload(db, actor, identifier, body, kind)
