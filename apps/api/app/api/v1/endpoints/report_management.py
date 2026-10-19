"""Authenticated report maintenance; previews never persist uploaded PDFs."""
from typing import Literal
from uuid import UUID
from urllib.parse import quote
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.deps import require_management
from app.api.v1.endpoints.education import writer, write
from app.schemas.report_management import PdfUpload, Classification, Batch, Replacement, ReportDelete
from app.services import report_management as service
from app.services.education_common import audit

router = APIRouter(prefix="/platform/education/report-management", tags=["report-management"])
admin_reader = require_management("SCHOOL_ADMIN", "SUPER_ADMIN", "QA")


def private_response(content, media_type, filename=None):
    return Response(content, media_type=media_type, headers={"Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff", **({"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename)} if filename else {})})


@router.get("/options")
async def options(actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)):
    return await service.options(db, actor)


@router.get("/exams/{identifier}")
async def exam_options(identifier: UUID, actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)):
    return await service.exam_options(db, actor, identifier)


@router.post("/exams/{identifier}/naming-list")
async def naming_list(identifier: UUID, body: Classification, actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)):
    config = await service.exam_options(db, actor, identifier)
    content = service.naming_csv(config["exam_code"], config, body)
    return private_response(content, "text/csv; charset=utf-8", "报告文件命名清单_" + config["exam_code"] + ".csv")


@router.post("/inspect-pdf")
async def inspect_pdf(body: PdfUpload, actor=Depends(admin_reader)):
    return service.inspect_pdf(body)


@router.post("/pdf-preview")
async def pdf_preview(body: PdfUpload, page: int = Query(1, ge=1, le=100), actor=Depends(admin_reader)):
    content, _, _ = service.pdf(body)
    return private_response(service.render_pdf(content, page), "image/png")


@router.post("/batches/preview")
async def batch_preview(body: Batch, actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)):
    return await service.batch_preview(db, actor, body)


@router.post("/batches")
async def batch_save(body: Batch, key: UUID | None = Header(None, alias="Idempotency-Key"),
                     actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, service.batch_save(db, actor, body, key))


@router.get("/operations")
async def operations(page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=100),
                     actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)):
    return await service.logs(db, actor, page, page_size)


@router.get("/access-check")
async def access_check(exam_id: UUID, kind: Literal["teacher", "student"], recipient_id: UUID,
                       login: bool = True, actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)):
    return await service.access_check(db, actor, exam_id, kind, recipient_id, login)


@router.get("")
async def listing(category: Literal["", "diagnostic", "essay"] = "", exam_id: UUID | None = None,
                  report_type: str = Query("", max_length=30), subject: str = Query("", max_length=100),
                  grade: str = Query("", max_length=100), cls: str = Query("", max_length=250), search: str = Query("", max_length=200),
                  page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=100),
                  actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)):
    return await service.listing(db, actor, category, exam_id, report_type, subject, grade, cls, search, page, page_size)


@router.post("/delete")
async def remove(body: ReportDelete, key: UUID | None = Header(None, alias="Idempotency-Key"),
                 actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, service.remove(db, actor, body, key))


@router.get("/{identifier}")
async def detail(identifier: UUID, actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)):
    return await service.detail(db, actor, identifier)


@router.post("/{identifier}/replace")
async def replace(identifier: UUID, body: Replacement, key: UUID | None = Header(None, alias="Idempotency-Key"),
                  actor=Depends(writer), db: AsyncSession = Depends(get_db)):
    return await write(db, service.replace(db, actor, identifier, body, key))


@router.get("/{identifier}/file")
async def report_file(identifier: UUID, version: int | None = Query(None, ge=1), page: int | None = Query(None, ge=1, le=100),
                      actor=Depends(admin_reader), db: AsyncSession = Depends(get_db)):
    report = await service.current_report(db, actor, identifier)
    file = await service.current_file(db, actor, report, version, include_content=True)
    content = service.render_pdf(file.content, page) if page else file.content
    audit(db, actor, "report-management.read", report, {"version": file.version, "page": page})
    await db.commit()
    return private_response(content, "image/png" if page else "application/pdf", None if page else file.filename)
