import pytest

from app.services.exam_permission_defaults import teacher_defaults


@pytest.fixture
def configuration():
    people = {
        "student-5": {"grade": "高中一年级", "class_number": "5", "class_id": "class-5"},
        "student-26": {"grade": "高中一年级", "class_number": "26班", "class_id": None},
        "student-11": {"grade": "高中二年级", "class_number": "1", "class_id": "class-11"},
    }
    return {"snapshots": people, "subjects": [
        {"subject_id": "chinese", "name": "语文", "student_ids": list(people)},
        {"subject_id": "math", "name": "数学", "student_ids": list(people)},
        {"subject_id": "history", "name": "历史", "student_ids": list(people)},
    ]}


def recommend(configuration, fields=None, duties=None, assignments=None, ready=("chinese", "math")):
    return teacher_defaults({"id": "teacher", "fields": fields or {}, "duties": duties or ["TEACHER"],
                             "assignments": assignments or []}, configuration, set(ready))


def test_subject_teacher_uses_teaching_subjects_and_classes(configuration):
    result = recommend(configuration, {"任课年级班级": "历史:10.5；语文:11.1"})
    form = result["recommendation"]
    assert form["score_types"] == ["student", "classSubject"]
    assert form["score_subjects"] == ["chinese"]
    assert form["diagnosis_subjects"] == ["chinese", "history"]
    assert form["classes"] == ["高中一年级 / 5", "高中二年级 / 1"]
    assert form["range_type"] == "class" and form["essay_types"] == []


@pytest.mark.parametrize("homeroom", ["10.26", "高中一年级26班"])
def test_homeroom_defaults_include_combined_results_and_all_exam_subjects(configuration, homeroom):
    result = recommend(configuration, {"班主任年级班级": homeroom})
    form = result["recommendation"]
    assert "HOMEROOM_TEACHER" in result["duties"]
    assert "班主任" in result["role_labels"]
    assert form["score_types"] == ["student", "classSubject", "classAll"]
    assert form["diagnosis_types"] == ["student", "classSubject", "classAll"]
    assert form["score_subjects"] == ["chinese", "math"]
    assert form["diagnosis_subjects"] == ["chinese", "math", "history"]
    assert form["classes"] == ["高中一年级 / 26班"]


def test_subject_leader_matches_numeric_grade_and_subject_without_class_ids(configuration):
    form = recommend(configuration, {"教研组长负责年级科目": "10.数学,11.语文"})["recommendation"]
    assert form["score_types"] == ["student", "classSubject", "gradeSubject"]
    assert form["score_subjects"] == ["chinese", "math"]
    assert form["range_type"] == "grade"
    assert form["grades"] == ["高中一年级", "高中二年级"]


def test_grade_leader_gets_all_subjects_only_in_responsible_grades(configuration):
    form = recommend(configuration, {"年级长负责年级": "10"})["recommendation"]
    assert form["range_type"] == "grade" and form["grades"] == ["高中一年级"]
    assert form["score_types"] == ["student", "classSubject", "gradeSubject", "classAll", "gradeAll"]
    assert "school" not in form["diagnosis_types"]


@pytest.mark.parametrize("role", ["ACADEMIC_DIRECTOR", "PRINCIPAL", "GENERAL_DIRECTOR", "SCHOOL_VIEWER"])
def test_school_roles_have_complete_defaults(configuration, role):
    form = recommend(configuration, duties=["TEACHER", role])["recommendation"]
    assert form["range_type"] == "all"
    assert form["score_types"] == ["student", "classSubject", "gradeSubject", "classAll", "gradeAll", "school"]
    assert form["diagnosis_subjects"] == ["chinese", "math", "history"]


def test_combined_roles_include_homeroom_types_when_homeroom_not_in_exam(configuration):
    form = recommend(configuration, {"任课年级班级": "历史:10.5", "班主任年级班级": "10.99"})["recommendation"]
    assert "classAll" in form["score_types"] and "classAll" in form["diagnosis_types"]
    assert form["classes"] == ["高中一年级 / 5"]
    assert form["score_subjects"] == ["chinese", "math"]


def test_combined_class_and_grade_roles_keep_the_exact_union_of_student_ranges(configuration):
    result = recommend(configuration, {"教研组长负责年级科目": "11.数学", "任课年级班级": "语文:10.5"})
    form = result["recommendation"]
    assert form["range_type"] == "class"
    assert form["classes"] == ["高中一年级 / 5", "高中二年级 / 1"]
    assert "高中一年级 / 26班" not in result["scope_classes"]


def test_legacy_assignment_fallback_and_missing_references(configuration):
    legacy = recommend(configuration, assignments=[{"class_id": "class-5", "subject_id": "math"}])
    assert legacy["recommendation"]["score_subjects"] == ["math"]
    assert legacy["recommendation"]["classes"] == ["高中一年级 / 5"]
    missing = recommend(configuration, {"任课年级班级": "化学:12.9"})
    assert missing["recommendation"]["classes"] == []
    assert missing["recommendation"]["score_types"] == []
    assert len(missing["default_warnings"]) == 2


def test_no_imported_scores_does_not_generate_invalid_score_defaults(configuration):
    form = recommend(configuration, {"班主任年级班级": "10.26"}, ready=())["recommendation"]
    assert form["score_types"] == [] and form["score_subjects"] == []
    assert "classAll" in form["diagnosis_types"]


def test_filter_classes_do_not_inherit_subject_leader_authorization(configuration):
    result = recommend(configuration, {"任课年级班级": "英语:10.22", "教研组长负责年级科目": "10.英语"})
    assert set(result["scope_classes"]) == {"高中一年级 / 5", "高中一年级 / 26班"}
    direct = [scope for scope in result["filter_scopes"] if scope["class_number"]]
    assert direct == [{"role": "TEACHER", "grade": "高中一年级", "class_number": "22", "subject": "英语"}]


def test_filter_classes_do_not_inherit_school_authorization(configuration):
    result = recommend(configuration, {"任课年级班级": "英语:10.22", "是否教务主任": "是"})
    assert result["recommendation"]["range_type"] == "all"
    assert {scope["class_number"] for scope in result["filter_scopes"]} == {"22"}


def test_filter_scopes_keep_class_grade_subject_pairs_and_real_homerooms(configuration):
    result = recommend(configuration, {"任课年级班级": "语文:10.05;数学:11.1", "班主任年级班级": "高中一年级26班"})
    assert result["filter_scopes"] == [
        {"role": "TEACHER", "grade": "高中一年级", "class_number": "5", "subject": "语文"},
        {"role": "TEACHER", "grade": "高中二年级", "class_number": "1", "subject": "数学"},
        {"role": "HOMEROOM_TEACHER", "grade": "高中一年级", "class_number": "26", "subject": ""},
    ]


def test_filter_scope_fallback_uses_only_explicit_legacy_assignments(configuration):
    assignments = [{"class_id": "class-5", "subject_id": "math"}]
    result = recommend(configuration, assignments=assignments)
    assert result["filter_scopes"] == [{"role": "TEACHER", "grade": "高中一年级", "class_number": "5", "subject": "数学"}]
    leader = recommend(configuration, duties=["TEACHER", "PRINCIPAL"], assignments=assignments)
    assert not leader["filter_scopes"]
