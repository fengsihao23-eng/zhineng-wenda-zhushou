"""Large real PDF batches use bounded transfers and one atomic report save."""
import base64
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy import func, select, update
from app.db.models import User, Student, StudentYearClass
from app.db.models.report_management import ManagedReport, ReportFile, ReportOperation, StagedReportPdf
from app.schemas.report_management import Classification
from app.services import report_management as service
from app.services.education_common import now
from test_education_workbench import actors  # noqa: F401
from test_exam_management import exam_people, create, switch  # noqa: F401
from test_report_management import ROOT, pdf_bytes, upload, post, report_row


@pytest.mark.asyncio
async def test_500_reports_over_30mb_save_atomically_and_retry_without_duplicates(client, test_db, actors, exam_people):
    extra_users = [User(id=uuid4(), school_id=actors['school'].id, username=f'bulk-{i}', password_hash='unused', display_name=f'合成学生{i}') for i in range(497)]
    test_db.add_all(extra_users)
    await test_db.flush()
    extra_students = [Student(id=uuid4(), school_id=user.school_id, user_id=user.id, name=user.display_name) for user in extra_users]
    test_db.add_all(extra_students)
    await test_db.flush()
    test_db.add_all([StudentYearClass(school_id=student.school_id, student_id=student.id, academic_year='2026-2027', grade='高中一年级', class_number=f'{i // 50 + 1}班') for i, student in enumerate(extra_students)])
    await test_db.commit()
    people = exam_people + [SimpleNamespace(id=student.id) for student in extra_students]
    exam = await create(client, people, count=500, subjects=1)
    scope = (await client.get(ROOT + '/exams/' + exam['id'])).json()
    classification = Classification(category='diagnostic', report_type='student', subject_ids=[exam['subjects'][0]['subject_id']])
    # Valid PDFs padded with trailing comments exceed the former total limit.
    pdf = pdf_bytes(pages=1) + b'\n%' + b'x' * 80_000 + b'\n'
    rows = []
    for offset in range(0, 500, 20):
        targets = scope['subjects'][0]['student_ids'][offset:offset + 20]
        files = [upload(service.filename_for(scope['exam_code'], scope, classification, sid), pdf) for sid in targets]
        transferred = (await post(client, '/uploads', {'files': files}))['files']
        assert len(transferred) == len(files) and all(row.get('asset_id') for row in transferred)
        rows.extend([{**classification.model_dump(mode='json'), 'target_key': sid,
                      'file': {'filename': file['filename'], 'asset_id': file['asset_id']},
                      'naming': classification.model_dump(mode='json'), 'previewed': True} for sid, file in zip(targets, transferred)])
    assert await test_db.scalar(select(func.count()).select_from(StagedReportPdf)) == 500
    assert await test_db.scalar(select(func.count()).select_from(ManagedReport)) == 0
    body = {'exam_id': exam['id'], 'expected_exam_revision': exam['revision'], 'reports': rows}
    assert (await client.post(ROOT + '/batches/preview', json={**body, 'reports': rows + [rows[0]]})).status_code == 422
    preview = await post(client, '/batches/preview', body)
    assert preview['count'] == 500
    assert sum(row['file_size'] for row in preview['reports']) > 30 * 1024 * 1024
    bad = {**rows[-1], 'previewed': False}
    await post(client, '/batches', {**body, 'reports': rows[:-1] + [bad], 'preview_hash': preview['preview_hash']}, 422)
    assert await test_db.scalar(select(func.count()).select_from(ManagedReport)) == 0
    assert await test_db.scalar(select(func.count()).select_from(StagedReportPdf)) == 500
    key = uuid4()
    result = await post(client, '/batches', {**body, 'preview_hash': preview['preview_hash']}, key=key)
    again = await post(client, '/batches', {**body, 'preview_hash': preview['preview_hash']}, key=key)
    assert result == again and result['count'] == 500
    assert await test_db.scalar(select(func.count()).select_from(ManagedReport)) == 500
    assert await test_db.scalar(select(func.count()).select_from(ReportFile)) == 500
    assert await test_db.scalar(select(func.count()).select_from(ReportOperation)) == 1
    assert await test_db.scalar(select(func.count()).select_from(StagedReportPdf)) == 0
    downloaded = await client.get(ROOT + '/' + result['reports'][-1]['id'] + '/file')
    assert downloaded.content == pdf


@pytest.mark.asyncio
async def test_temporary_uploads_require_the_owner_and_filename_and_expire(client, test_db, actors, exam_people):
    exam = await create(client, exam_people)
    row = await report_row(client, exam)
    transfer = (await post(client, '/uploads', {'files': [row['file'], upload('broken.pdf', b'bad')]}))['files']
    assert transfer[0].get('asset_id') and transfer[1].get('error')
    file = {'filename': row['file']['filename'], 'asset_id': transfer[0]['asset_id']}
    preview = await client.post(ROOT + '/pdf-preview?page=1', json=file)
    assert preview.status_code == 200 and preview.content.startswith(b'\x89PNG')
    await post(client, '/pdf-preview', {**file, 'filename': 'renamed.pdf'}, 422)
    switch(actors, test_db, 'foreign')
    await post(client, '/pdf-preview', file, 422)
    await post(client, '/uploads/discard', {'asset_ids': [file['asset_id']]})
    assert await test_db.scalar(select(func.count()).select_from(StagedReportPdf)) == 1
    switch(actors, test_db, 'admin')
    await test_db.execute(update(StagedReportPdf).values(user_id=actors['teacher'].id))
    await test_db.commit()
    await post(client, '/pdf-preview', file, 422)
    await test_db.execute(update(StagedReportPdf).values(user_id=actors['admin'].id, expires_at=now() - timedelta(seconds=1)))
    await test_db.commit()
    await post(client, '/pdf-preview', file, 422)
    await post(client, '/uploads', {'files': [row['file']]})
    assert await test_db.scalar(select(func.count()).select_from(StagedReportPdf)) == 1
    ids = list(await test_db.scalars(select(StagedReportPdf.id)))
    await post(client, '/uploads/discard', {'asset_ids': list(map(str, ids))})
    assert await test_db.scalar(select(func.count()).select_from(StagedReportPdf)) == 0


@pytest.mark.asyncio
async def test_upload_transfer_limits_do_not_create_partial_temporary_files(client, test_db, actors):
    file = upload('synthetic.pdf', pdf_bytes(pages=1))
    assert (await client.post(ROOT + '/uploads', json={'files': [file] * 21})).status_code == 422
    large = {'filename': 'synthetic.pdf', 'content_base64': base64.b64encode(b'x' * (11 * 1024 * 1024)).decode()}
    await post(client, '/uploads', {'files': [large, large]}, 422)
    assert await test_db.scalar(select(func.count()).select_from(StagedReportPdf)) == 0
