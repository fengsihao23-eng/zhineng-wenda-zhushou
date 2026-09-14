from pathlib import Path

from app.data.csv_importer import validate_csv_directory


def _write_batch(root: Path, duplicate_student: bool = False) -> None:
    files = {
        "schools.csv": "external_school_id,name,code\ns1,示例学校,S1\n",
        "students.csv": "external_student_id,school_code,student_no,name\n" +
        ("u1,S1,001,张三\nu1,S1,002,李四\n" if duplicate_student else "u1,S1,001,张三\n"),
        "classes.csv": "external_class_id,school_code,name\nc1,S1,一班\n",
        "exams.csv": "external_exam_id,school_code,name,exam_type\ne1,S1,期中考试,midterm\n",
        "subjects.csv": "external_subject_id,school_code,code,name\nsub1,S1,MATH,数学\n",
        "student_exam_scores.csv": "external_student_id,external_exam_id,school_code,total_score\nu1,e1,S1,120\n",
        "student_subject_scores.csv": "external_student_id,external_exam_id,external_subject_id,school_code,score,full_score\nu1,e1,sub1,S1,90,100\n",
        "question_scores.csv": "external_student_id,external_exam_id,external_subject_id,school_code,question_no,score,full_score,lost_score\nu1,e1,sub1,S1,1,8,10,2\n",
    }
    for name, content in files.items():
        (root / name).write_text(content, encoding="utf-8")


def test_csv_batch_validates():
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write_batch(root)
        report = validate_csv_directory(root, "batch-1")
        assert report.ok
        assert report.files["students.csv"] == 1


def test_csv_batch_rejects_duplicate_student():
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write_batch(root, duplicate_student=True)
        report = validate_csv_directory(root, "batch-2")
        assert not report.ok
        assert any(issue.code == "DUPLICATE_STUDENT" for issue in report.issues)
