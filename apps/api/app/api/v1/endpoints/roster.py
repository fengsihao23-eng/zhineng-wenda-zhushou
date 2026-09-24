"""Roster endpoints follow the four approved teacher/student maintenance flows."""
from uuid import UUID
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_management
from app.api.v1.endpoints.education import writer, write
from app.core.database import get_db
from app.db.models.roster import RosterImport
from app.schemas.roster import RosterKind, RosterUpload, RosterConfirm, RosterAction
from app.services import roster_workbench as roster
from app.services.roster_excel import student_error_template_bytes, student_template_bytes
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
    return excel((TEMPLATES / f"{kind}.xlsx").read_bytes(), "教师资料模板.xlsx")


@router.get("/teachers/error-template")
async def error_template(actor=Depends(reader)):
    return excel((TEMPLATES / "errors.xlsx").read_bytes(), "错误清单模板.xlsx")


@router.get("/students/error-template")
async def student_error_template(actor=Depends(reader)):
    return excel(student_error_template_bytes(), "学生错误清单模板.xlsx")


@router.get("/{kind}/records")
async def records(kind: RosterKind, search: str = Query("", max_length=100), phone: str = Query("", max_length=100), class_name: str = Query("", max_length=100), page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100), actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    return await roster.listing(db, actor, kind, search, phone, class_name, page, page_size)


@router.get("/teachers/deletions")
async def deletions(search: str = Query("", max_length=100), available: bool = False, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100), actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    return await roster.deletion_history(db, actor, search, available, page, page_size)


@router.get("/teachers/deletions/{identifier}")
async def deletion(identifier: UUID, actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    return await roster.deletion_detail(db, actor, identifier)


@router.get("/{kind}/imports")
async def batches(kind: RosterKind, actor=Depends(reader), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(RosterImport).where(RosterImport.school_id == actor.school_id, RosterImport.kind == kind).order_by(RosterImport.created_at.desc()).limit(100))).all()
    return [data(row, "id", "filename", "status", "operator_name", "created_at", "confirmed_at") for row in rows]


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


@router.post("/imports/{identifier}/confirm")
async def confirm(identifier: UUID, body: RosterConfirm, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, roster.confirm(db, actor, identifier, body))


@router.post("/{kind}/records/{identifier}/actions")
async def lifecycle(kind: RosterKind, identifier: UUID, body: RosterAction, actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, roster.lifecycle(db, actor, kind, identifier, body))
