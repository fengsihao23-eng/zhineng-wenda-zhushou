from pathlib import Path

from app.data.import_service import build_import_plan


def _write_batch(root: Path, *, bad_student_reference: bool = False) -> None:
    files = {
        "schools.csv": "external_school_id,name,code\ns1,示例学校,S1\n",
        "students.csv": "external_student_id,school_code,student_no,name\nu1,S1,001,张三\n",
        "classes.csv": "external_class_id,school_code,name\nc1,S1,一班\n",
        "exams.csv": "external_exam_id,school_code,name,exam_type\ne1,S1,期中考试,midterm\n",
        "subjects.csv": "external_subject_id,school_code,code,name\nsub1,S1,MATH,数学\n",
        "student_exam_scores.csv": (
            "external_student_id,external_exam_id,school_code,total_score\n"
            f"{'missing' if bad_student_reference else 'u1'},e1,S1,120\n"
        ),
        "student_subject_scores.csv": "external_student_id,external_exam_id,external_subject_id,school_code,score,full_score\nu1,e1,sub1,S1,90,100\n",
        "question_scores.csv": "external_student_id,external_exam_id,external_subject_id,school_code,question_no,score,full_score,lost_score\nu1,e1,sub1,S1,1,8,10,2\n",
    }
    for name, content in files.items():
        (root / name).write_text(content, encoding="utf-8")


def test_build_import_plan_is_complete_and_deterministic(tmp_path: Path):
    _write_batch(tmp_path)
    first = build_import_plan(tmp_path, "batch-1")
    second = build_import_plan(tmp_path, "batch-1")

    assert first.ok
    assert len(first.rows) == 8
    assert first.content_hash == second.content_hash


def test_build_import_plan_rejects_cross_file_reference(tmp_path: Path):
    _write_batch(tmp_path, bad_student_reference=True)
    plan = build_import_plan(tmp_path, "batch-2")

    assert not plan.ok
    assert any(issue.code == "STUDENT_NOT_FOUND" for issue in plan.issues)
