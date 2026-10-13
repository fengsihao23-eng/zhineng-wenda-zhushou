"""Roster endpoints follow the four approved teacher/student maintenance flows."""
from uuid import UUID
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import defer
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_management
from app.api.v1.endpoints.education import writer, write
from app.core.database import get_db
from app.db.models.roster import RosterImport
from app.schemas.roster import RosterKind, RosterUpload, RosterConfirm, RosterAction, TeacherDelete
from app.schemas.person_id import PersonReference
from app.services import roster_workbench as roster
from app.services import teacher_changes
from app.services import student_roster, student_tasks
from app.db.models.student_roster import StudentWorkflowTask
from app.schemas.student_roster import StudentTaskCreate, StudentTaskPrepare, StudentTaskConfirm, StudentTaskReview, StudentTaskCancel
from app.core.errors import ApiError
from app.services.roster_excel import student_error_template_bytes, student_template_bytes, teacher_template_bytes
from app.services.education_common import owned, data
TEMPLATES = Path(__file__).resolve().parents[3] / "resources" / "roster"

router = APIRouter(prefix="/platform/education/roster", tags=["roster"])
reader = require_management("SCHOOL_ADMIN", "SUPER_ADMIN", "QA", "SCHOOL_VIEWER")


def excel(content, filename):
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}", "Cache-Control": "no-store"})


@router.get("/{kind}/template")
async def template(kind: RosterKind, actor=Depends(reader)):
    if kind == "students":
        return excel(student_template_bytes(), "学生资料模板.xlsx")
    source = TEMPLATES / "teachers.xlsx"
    return excel(source.read_bytes() if source.is_file() else teacher_template_bytes(), "教师资料模板.xlsx")


@router.get("/teachers/error-template")
async def error_template(actor=Depends(reader)):
    return excel((TEMPLATES / "errors.xlsx").read_bytes(), "错误清单模板.xlsx")


@router.get("/students/error-template")
async def student_error_template(actor=Depends(reader)):
    return excel(student_error_template_bytes(), "学生错误清单模板.xlsx")


@router.get("/{kind}/records")
async def records(kind: RosterKind, search: str = Query("", max_length=100), phone: str = Query("", max_length=100), class_name: str = Query("", max_length=100), status: str = Query("", max_length=30), page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100), actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    if kind == "students":
        return await student_roster.listing(db, actor, search, class_name, status, page, page_size)
    return await roster.listing(db, actor, kind, search, phone, class_name, page, page_size)


@router.get("/teachers/deletions")
async def deletions(search: str = Query("", max_length=100), reason: str = Query("", max_length=30), available: bool = False, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100), actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    return await roster.deletion_history(db, actor, search, available, page, page_size, reason)


@router.post("/teachers/delete")
async def delete_teachers(body: TeacherDelete, key: UUID | None = Header(None, alias="Idempotency-Key"), actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, teacher_changes.delete_teachers(db, actor, body, key))


@router.get("/teachers/change-tasks/{identifier}")
async def change_task(identifier: UUID, actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    from app.db.models.roster import TeacherChangeTask
    return await teacher_changes.task_view(db, actor, await owned(db, TeacherChangeTask, identifier, actor))


@router.get("/teachers/change-tasks/{identifier}/template")
async def change_template(identifier: UUID, actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    response = excel(await teacher_changes.task_template(db, actor, identifier), f"教师变更原档案_任务{identifier}.xlsx")
    response.headers["X-Teacher-Task-ID"] = str(identifier)
    return response


@router.post("/teachers/change-tasks/{identifier}/imports")
async def change_upload(identifier: UUID, body: RosterUpload, key: UUID | None = Header(None, alias="Idempotency-Key"), actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, teacher_changes.upload_task(db, actor, identifier, body, key))


@router.get("/teachers/deletions/{identifier}")
async def deletion(identifier: UUID, actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    return await roster.deletion_detail(db, actor, identifier)


@router.get("/{kind}/imports")
async def batches(kind: RosterKind, search: str = Query("", max_length=100), paginated: bool = False, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    query = select(RosterImport, RosterImport.original_content.is_not(None).label("has_original")).options(defer(RosterImport.original_content)).where(RosterImport.school_id == actor.school_id, RosterImport.kind == kind).order_by(RosterImport.created_at.desc(), RosterImport.id)
    if not paginated:
        query = query.limit(100)
    rows = (await db.execute(query)).all()
    if search:
        rows = [(row, original) for row, original in rows if search in f"{row.id} {row.filename} {row.change_task_id or ''}" or any(search in f"{r['values'].get('教师姓名', r['values'].get('姓名', ''))} {r['values'].get('教师账号', r['values'].get('账号', ''))}" for r in row.rows)]
    total = len(rows)
    if paginated:
        rows = rows[(page - 1) * page_size:page * page_size]
    items = [{**data(row, "id", "filename", "status", "operator_name", "created_at", "confirmed_at", "change_task_id"), "has_original": original, "report": {k: row.report.get(k) for k in ("total_rows", "success_count", "skipped_count", "confirmed_by_name", "confirmed_at")}} for row, original in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size} if paginated else items


@router.post("/{kind}/imports")
async def upload(kind: RosterKind, body: RosterUpload, compact: bool = False, key: UUID | None = Header(None, alias="Idempotency-Key"), actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    result = await write(db, roster.upload(db, actor, kind, body, key))
    return {field: result[field] for field in ("id", "kind", "status", "revision")} if compact else result


@router.get("/imports/{identifier}")
async def detail(identifier: UUID, actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    return roster.view(await owned(db, RosterImport, identifier, actor))


@router.get("/imports/{identifier}/errors")
async def errors(identifier: UUID, actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    return excel(roster.errors_excel(await owned(db, RosterImport, identifier, actor)), "导入错误清单.xlsx")


@router.get("/imports/{identifier}/original")
async def original(identifier: UUID, actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    item = await owned(db, RosterImport, identifier, actor)
    if item.original_content is None:
        raise ApiError(404, "ORIGINAL_FILE_UNAVAILABLE", "该历史批次未保存原文件，可查看原始资料明细。")
    response = excel(item.original_content, item.filename)
    if item.filename.lower().endswith(".xls"):
        response.headers["content-type"] = "application/vnd.ms-excel"
    return response


@router.post("/imports/{identifier}/confirm")
async def confirm(identifier: UUID, body: RosterConfirm, compact: bool = False, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    result = await write(db, roster.confirm(db, actor, identifier, body))
    return {field: result[field] for field in ("id", "kind", "status", "revision")} if compact else result


@router.post("/{kind}/records/{identifier}/actions")
async def lifecycle(kind: RosterKind, identifier: UUID, body: RosterAction, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, roster.lifecycle(db, actor, kind, identifier, body))


@router.get("/students/context")
async def student_context(actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    return await student_roster.context(db, actor)


@router.get("/students/records/{identifier}")
async def student_detail(identifier: str, actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    return await student_roster.detail(db, actor, identifier)


@router.get("/students/archive-template")
async def student_archive_template(student_ids: list[PersonReference] = Query(default=[], max_length=5000), all_filtered: bool = False, search: str = Query("", max_length=100), class_name: str = Query("", max_length=100), actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    if all_filtered:
        result = await student_roster.listing(db, actor, search, class_name, "active", 1, 5000)
        if result["total"] > 5000:
            raise ApiError(413, "ROSTER_TOO_LARGE", "当前范围超过5000名学生，请缩小筛选后分批导出。")
        student_ids = [UUID(row["id"]) for row in result["items"]]
    return excel(await student_roster.archive_template(db, actor, student_ids), "学生档案变更模板.xlsx")


@router.get("/students/promotion-template")
async def student_promotion_template(actor=Depends(reader)):
    from app.services.roster_excel import STUDENT_PROMOTION_COLUMNS, workbook_bytes
    return excel(workbook_bytes(STUDENT_PROMOTION_COLUMNS), "学生升级换班名单.xlsx")


@router.get("/students/tasks")
async def student_tasks_list(search: str = Query("", max_length=100), kind: str = Query("", max_length=20), page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    return await student_roster.task_listing(db, actor, search, kind, page, page_size)


@router.post("/students/tasks")
async def student_task_create(body: StudentTaskCreate, key: UUID | None = Header(None, alias="Idempotency-Key"), actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, student_tasks.create(db, actor, body, key))


@router.get("/students/tasks/{identifier}")
async def student_task_detail(identifier: UUID, actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    return student_roster.task_view(await owned(db, StudentWorkflowTask, identifier, actor))


@router.get("/students/tasks/{identifier}/original")
async def student_task_original(identifier: UUID, actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    task = await owned(db, StudentWorkflowTask, identifier, actor)
    if task.original_content is None:
        raise ApiError(404, "ORIGINAL_FILE_UNAVAILABLE", "该办理事项未上传原文件，可查看办理明细。")
    response = excel(task.original_content, task.filename)
    if task.filename.lower().endswith(".xls"):
        response.headers["content-type"] = "application/vnd.ms-excel"
    return response


@router.get("/students/tasks/{identifier}/errors")
async def student_task_errors(identifier: UUID, actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    return excel(student_tasks.errors_excel(await owned(db, StudentWorkflowTask, identifier, actor)), "学生办理错误清单.xlsx")


@router.post("/students/tasks/{identifier}/prepare")
async def student_task_prepare(identifier: UUID, body: StudentTaskPrepare, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, student_tasks.prepare(db, actor, identifier, body))


@router.post("/students/tasks/{identifier}/review")
async def student_task_review(identifier: UUID, body: StudentTaskReview, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, student_tasks.review(db, actor, identifier, body))


@router.post("/students/tasks/{identifier}/confirm")
async def student_task_confirm(identifier: UUID, body: StudentTaskConfirm, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, student_tasks.confirm(db, actor, identifier, body))


@router.post("/students/tasks/{identifier}/cancel")
async def student_task_cancel(identifier: UUID, body: StudentTaskCancel, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, student_tasks.cancel(db, actor, identifier, body))
