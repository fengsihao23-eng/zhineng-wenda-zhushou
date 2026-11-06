"""Private, expiring PDF uploads; the final report batch contains only references."""
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import delete, func, insert, literal, select
from sqlalchemy.orm import defer
from app.core.errors import ApiError
from app.db.models import User
from app.db.models.report_management import ReportFile, StagedReportPdf
from app.schemas.report_management import MAX_BATCH_BYTES
from app.services.education_common import now

LIFETIME = timedelta(days=1)


def owned_files(actor):
    return (StagedReportPdf.school_id == actor.school_id, StagedReportPdf.user_id == actor.user_id)


async def reserve(db, actor, size):
    # Serialize transfers by the same operator, including across API workers.
    await db.scalar(select(User.id).where(User.id == actor.user_id).with_for_update())
    await db.execute(delete(StagedReportPdf).where(StagedReportPdf.expires_at < now()))
    used = await db.scalar(select(func.coalesce(func.sum(StagedReportPdf.file_size), 0)).where(*owned_files(actor)))
    if used + size > 2 * MAX_BATCH_BYTES:
        raise ApiError(413, "REPORT_UPLOAD_SPACE", "待保存的报告文件太多，请先保存或取消其他批次。")


def store(db, actor, filename, content, pages, content_hash):
    identifier = uuid4()
    db.add(StagedReportPdf(id=identifier, school_id=actor.school_id, user_id=actor.user_id,
        filename=filename, content=content, file_size=len(content), page_count=pages,
        content_hash=content_hash, expires_at=now() + LIFETIME))
    return {"filename": filename, "asset_id": str(identifier), "file_size": len(content),
            "page_count": pages, "content_hash": content_hash}


async def metadata(db, actor, identifiers):
    if not identifiers:
        return {}
    rows = (await db.scalars(select(StagedReportPdf).options(defer(StagedReportPdf.content)).where(
        StagedReportPdf.id.in_(identifiers), *owned_files(actor), StagedReportPdf.expires_at >= now()).with_for_update())).all()
    return {row.id: row for row in rows}


def unavailable():
    return ApiError(422, "REPORT_UPLOAD_EXPIRED", "上传文件已失效或无权访问，请重新选择该 PDF 文件。")


def checked(assets, upload):
    asset = assets.get(upload.asset_id)
    if asset is None:
        raise unavailable()
    if asset.filename != upload.filename:
        raise ApiError(422, "REPORT_UPLOAD_CHANGED", "上传文件名已变化，请重新选择该 PDF 文件。")
    return asset


async def content(db, actor, upload):
    binary = await db.scalar(select(StagedReportPdf.content).where(StagedReportPdf.id == upload.asset_id,
        *owned_files(actor), StagedReportPdf.filename == upload.filename, StagedReportPdf.expires_at >= now()))
    if binary is None:
        raise unavailable()
    return binary


async def copy_to_report(db, actor, file, asset_id):
    # Keep the PDF binary inside PostgreSQL; loading hundreds into the API
    # process would exceed its memory even though transfers are small.
    table = ReportFile.__table__
    columns = ["id", "school_id", "report_id", "version", "filename", "content", "file_size",
               "page_count", "content_hash", "reason", "operator_name", "created_at"]
    values = [StagedReportPdf.content if key == "content" else literal(getattr(file, key), type_=table.c[key].type)
              for key in columns]
    result = await db.execute(insert(table).from_select(columns, select(*values).where(
        StagedReportPdf.id == asset_id, *owned_files(actor))))
    if result.rowcount != 1:
        raise unavailable()


async def consume(db, actor, identifiers):
    if identifiers:
        await db.execute(delete(StagedReportPdf).where(StagedReportPdf.id.in_(identifiers), *owned_files(actor)))
