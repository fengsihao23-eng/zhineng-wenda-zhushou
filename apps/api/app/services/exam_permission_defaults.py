import re

from app.services.roster_excel import GRADE_NAMES, duty_codes, subject_leadership, teaching_pairs


DEFAULT_RULES = [
    {"role": "TEACHER", "label": "任课教师", "types": ["student", "classSubject"],
     "subjects": "任教学科", "scope": "任教班级"},
    {"role": "HOMEROOM_TEACHER", "label": "班主任", "types": ["student", "classSubject", "classAll"],
     "subjects": "本次考试全部科目", "scope": "班主任负责班级"},
    {"role": "SUBJECT_LEADER", "label": "教研组长", "types": ["student", "classSubject", "gradeSubject"],
     "subjects": "负责学科", "scope": "负责年级"},
    {"role": "GRADE_LEADER", "label": "年级长", "types": ["student", "classSubject", "gradeSubject", "classAll", "gradeAll"],
     "subjects": "本次考试全部科目", "scope": "负责年级"},
    {"role": "ACADEMIC_DIRECTOR", "label": "教务主任", "types": ["student", "classSubject", "gradeSubject", "classAll", "gradeAll", "school"],
     "subjects": "本次考试全部科目", "scope": "全部参试学生"},
    {"role": "PRINCIPAL", "label": "校长", "types": ["student", "classSubject", "gradeSubject", "classAll", "gradeAll", "school"],
     "subjects": "本次考试全部科目", "scope": "全部参试学生"},
    {"role": "GENERAL_DIRECTOR", "label": "总务主任", "types": ["student", "classSubject", "gradeSubject", "classAll", "gradeAll", "school"],
     "subjects": "本次考试全部科目", "scope": "全部参试学生"},
    {"role": "SCHOOL_VIEWER", "label": "全校数据查看", "types": ["student", "classSubject", "gradeSubject", "classAll", "gradeAll", "school"],
     "subjects": "本次考试全部科目", "scope": "全部参试学生"},
]


def grade_name(value):
    value = str(value).strip()
    return GRADE_NAMES.get(int(value), value) if value.isdigit() else value


def class_matches(person, grade, number):
    return grade_name(person["grade"]) == grade_name(grade) and person["class_number"].removesuffix("班").strip() == str(number)


def teacher_defaults(teacher, config, ready):
    fields = teacher.get("fields") or {}
    duties = set(teacher.get("duties") or []) | set(duty_codes(fields))
    rules = [rule for rule in DEFAULT_RULES if rule["role"] in duties]
    participant_ids = {identifier for subject in config["subjects"] for identifier in subject["student_ids"]}
    people = [person for identifier, person in config["snapshots"].items() if identifier in participant_ids]
    class_keys = {person["grade"] + " / " + person["class_number"] for person in people}
    subject_ids = {subject["subject_id"] for subject in config["subjects"]}
    subjects, classes, types, role_labels = set(), set(), set(), []
    has_grade_scope, has_school_scope = False, False
    teaching = teaching_pairs(fields.get("任课年级班级", "").replace("；", ";").replace("，", ","))
    homerooms = [tuple(map(int, match)) for match in re.findall(r"(?<!\d)(\d+)\.(\d+)(?!\d)", fields.get("班主任年级班级", ""))]
    for label in GRADE_NAMES.values():
        homerooms.extend((label, int(number)) for number in re.findall(re.escape(label) + r"\s*(\d+)班", fields.get("班主任年级班级", "")))
    leaders = subject_leadership(fields.get("教研组长负责年级科目", ""))
    grade_values = {grade_name(value) for value in re.split(r"[,，;；\s]+", fields.get("年级长负责年级", "")) if value}
    for rule in rules:
        role = rule["role"]
        role_classes, role_subjects = set(), set()
        if role == "TEACHER":
            role_subjects = {subject["subject_id"] for subject in config["subjects"] if any(subject["name"] == name for name, _, _ in teaching)}
            role_classes = {person["grade"] + " / " + person["class_number"] for person in people
                            if any(class_matches(person, grade, number) for _, grade, number in teaching)}
            if not teaching and not duties.intersection({"HOMEROOM_TEACHER", "SUBJECT_LEADER", "GRADE_LEADER"}):
                assignments = teacher.get("assignments") or []
                role_subjects = subject_ids.intersection(assignment["subject_id"] for assignment in assignments)
                role_classes = {person["grade"] + " / " + person["class_number"] for person in people
                                if any(person.get("class_id") == assignment["class_id"] for assignment in assignments)}
        elif role == "HOMEROOM_TEACHER":
            role_subjects = subject_ids
            role_classes = {person["grade"] + " / " + person["class_number"] for person in people
                            if any(class_matches(person, grade, number) for grade, number in homerooms)}
        elif role == "SUBJECT_LEADER":
            role_subjects = {subject["subject_id"] for subject in config["subjects"] if any(subject["name"] == name for _, name in leaders)}
            role_classes = {person["grade"] + " / " + person["class_number"] for person in people
                            if any(grade_name(person["grade"]) == grade_name(grade) for grade, _ in leaders)}
            has_grade_scope = True
        elif role == "GRADE_LEADER":
            role_subjects = subject_ids
            role_classes = {person["grade"] + " / " + person["class_number"] for person in people if grade_name(person["grade"]) in grade_values}
            has_grade_scope = True
        else:
            role_subjects, role_classes = subject_ids, class_keys
            has_school_scope = True
        role_labels.append(rule["label"])
        subjects.update(role_subjects)
        classes.update(role_classes)
        types.update(rule["types"])
    grades = {person["grade"] for person in people if person["grade"] + " / " + person["class_number"] in classes}
    full_grades = {person["grade"] + " / " + person["class_number"] for person in people if person["grade"] in grades}
    range_type = "all" if has_school_scope else "grade" if has_grade_scope and classes and classes == full_grades else "class"
    ordered_types = [value for value in DEFAULT_RULES[-1]["types"] if value in types]
    ordered_subjects = [subject["subject_id"] for subject in config["subjects"] if subject["subject_id"] in subjects]
    score_subjects = [identifier for identifier in ordered_subjects if identifier in ready]
    warnings = []
    if not classes:
        warnings.append("角色负责范围与本次参试名单没有匹配，请手动选择学生范围。")
    if not subjects:
        warnings.append("角色学科与本次考试科目没有匹配，请手动选择查询类型与科目。")
    return {"duties": sorted(duties), "role_labels": role_labels,
            "scope_classes": sorted(classes), "scope_grades": sorted(grades), "scope_subject_ids": ordered_subjects,
            "default_warnings": warnings,
            "recommendation": {"teacher_id": teacher["id"], "score_types": ordered_types if score_subjects else [],
                "score_subjects": score_subjects, "diagnosis_types": ordered_types if ordered_subjects else [],
                "diagnosis_subjects": ordered_subjects, "essay_types": [], "range_type": range_type,
                "grades": sorted(grades) if range_type == "grade" else [], "classes": sorted(classes) if range_type == "class" else []}}
