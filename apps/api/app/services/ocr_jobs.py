"""Durable OCR tasks using a local Tesseract executable; never fabricated text.

API enqueue and worker are separate transactions. A worker holds the job row
lock while recognizing; another worker skips it. A crashed worker rolls back,
so the persisted running row is recoverable by the next worker pass.
"""
import asyncio
import io
import shutil
import subprocess
from sqlalchemy import select, func
from app.core.errors import ApiError
from app.db.models.education import OcrJob, PaperDraft, PaperVersion, PrivateAsset
from app.services.education_common import claim, owned, native_only, now, audit, data
from app.services.curriculum import draft_detail, render_page


def capabilities():
    return {
        "engine": "tesseract",
        "available": bool(shutil.which("tesseract")),
        "mode": "local_worker",
        "message": "已检测到本地 OCR 引擎，语言包会在任务中校验。"
        if shutil.which("tesseract")
        else "未安装 Tesseract；任务会明确失败，可人工填写草稿后确认发布。",
    }


def recognize(asset, entries):
    executable = shutil.which("tesseract")
    if not executable:
        raise RuntimeError("OCR_ENGINE_UNAVAILABLE")
    languages = subprocess.run(
        [executable, "--list-langs"], capture_output=True, timeout=10, check=False
    )
    available = set(languages.stdout.decode("utf-8", errors="replace").splitlines())
    if languages.returncode or not {"chi_sim", "eng"}.issubset(available):
        raise RuntimeError("OCR_LANGUAGE_UNAVAILABLE")
    results = []
    for entry in entries:
        text = []
        for region in entry["regions"]:
            image = render_page(asset, region["page"])
            width, height = image.size
            crop = image.crop(
                (
                    int(region["x"] * width),
                    int(region["y"] * height),
                    int((region["x"] + region["width"]) * width),
                    int((region["y"] + region["height"]) * height),
                )
            )
            buffer = io.BytesIO()
            crop.save(buffer, format="PNG")
            try:
                result = subprocess.run(
                    [executable, "stdin", "stdout", "-l", "chi_sim+eng", "--psm", "6"],
                    input=buffer.getvalue(),
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError("OCR_TIMEOUT")
            if result.returncode:
                raise RuntimeError("OCR_ENGINE_FAILED")
            text.append(result.stdout.decode("utf-8", errors="replace").strip())
        results.append(
            {"key": entry["key"], "text": "\n".join(text), "requires_review": True}
        )
    return results


async def enqueue(db, actor, version_id, body, key):
    paper, draft = await draft_detail(db, actor, version_id, lock=True)
    native_only(paper)
    if draft.revision != body.expected_revision or draft.published_revision is not None:
        raise ApiError(409, "VERSION_CONFLICT", "草稿已更新或发布，请刷新后再发起识别。")
    if not draft.entries:
        raise ApiError(422, "OCR_REGIONS_REQUIRED", "请先框选并保存至少一个区域。")
    latest = await db.scalar(
        select(OcrJob)
        .where(OcrJob.draft_id == draft.id, OcrJob.draft_revision == draft.revision)
        .order_by(OcrJob.attempt.desc())
        .limit(1)
    )
    if latest and latest.status != "failed":
        return data(
            latest,
            "id",
            "status",
            "attempt",
            "progress",
            "result",
            "error_code",
            "draft_revision",
        )
    identifier, fresh = await claim(
        db, actor, f"ocr.enqueue.{draft.id}", key, body.model_dump()
    )
    if fresh:
        attempt = latest.attempt + 1 if latest else 1
        if attempt > 5:
            raise ApiError(409, "OCR_RETRY_LIMIT", "该草稿版本已重试五次，请修正配置或改用人工录入。")
        item = OcrJob(
            id=identifier,
            school_id=actor.school_id,
            draft_id=draft.id,
            draft_revision=draft.revision,
            input_entries=draft.entries,
            status="running",
            attempt=attempt,
        )
        db.add(item)
        audit(db, actor, "ocr.enqueue", item)
        await db.commit()
    return data(
        await owned(db, OcrJob, identifier, actor),
        "id",
        "status",
        "attempt",
        "progress",
        "result",
        "error_code",
        "draft_revision",
    )


async def execute_ocr(factory, identifier):
    async with factory() as db:
        async with db.begin():
            job = await db.scalar(
                select(OcrJob)
                .where(
                    OcrJob.id == identifier, OcrJob.status.in_(["queued", "running"])
                )
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return
            draft = await db.get(PaperDraft, job.draft_id)
            version = await db.get(PaperVersion, draft.paper_version_id)
            asset = await db.get(PrivateAsset, version.asset_id)
            try:
                result = await asyncio.to_thread(recognize, asset, job.input_entries)
                job.result = result
                job.progress = 100
                job.status = "succeeded"
                job.error_code = None
            except Exception as error:
                code = str(error)
                job.error_code = (
                    code
                    if code
                    in {
                        "OCR_ENGINE_UNAVAILABLE",
                        "OCR_LANGUAGE_UNAVAILABLE",
                        "OCR_TIMEOUT",
                        "OCR_ENGINE_FAILED",
                    }
                    else "OCR_INPUT_FAILED"
                )
                job.status = "failed"
            job.finished_at = now()
