from app.services.roster_excel import (GRADE_NAMES, duty_codes, subject_leadership, teaching_pairs,
                                      normalized, parse_class_reference, class_references, grade_codes)


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
    value = normalized(value)
    return GRADE_NAMES.get(int(value), value) if value.isdigit() else value


def class_number(value):
    value = normalized(value).removesuffix("班").strip()
    return str(int(value)) if value.isdigit() else value


def class_reference(value):
    """Read the same numeric or displayed class references used by roster imports."""
    reference = parse_class_reference(value)
    return (grade_name(reference[0]), str(reference[1])) if reference else ("", "")


def class_matches(person, grade, number):
    return grade_name(person["grade"]) == grade_name(grade) and class_number(person["class_number"]) == class_number(number)


def teacher_defaults(teacher, config, ready):
    fields = {key: normalized(value) for key, value in (teacher.get("fields") or {}).items()}
    duties = set(teacher.get("duties") or []) | set(duty_codes(fields))
    rules = [rule for rule in DEFAULT_RULES if rule["role"] in duties]
    participant_ids = {identifier for subject in config["subjects"] for identifier in subject["student_ids"]}
    people = {identifier: person for identifier, person in config["snapshots"].items() if identifier in participant_ids}
    classes_by_student = {identifier: person["grade"] + " / " + person["class_number"] for identifier, person in people.items()}
    subjects, classes, types = set(), set(), set()
    has_grade_scope, has_school_scope = False, False
    teaching = teaching_pairs(fields.get("任课年级班级", "").replace("\n", ";"))
    homerooms = class_references(fields.get("班主任年级班级", ""))
    leaders = subject_leadership(fields.get("教研组长负责年级科目", ""))
    grade_values = {grade_name(value) for value in grade_codes(fields.get("年级长负责年级", ""))}
    filter_scopes = []

    def add_filter_scope(role, grade, number="", subject=""):
        scope = {"role": role, "grade": grade_name(grade), "class_number": class_number(number), "subject": normalized(subject)}
        if scope not in filter_scopes:
            filter_scopes.append(scope)

    for subject, grade, number in teaching:
        add_filter_scope("TEACHER", grade, number, subject)
    for grade, number in homerooms:
        add_filter_scope("HOMEROOM_TEACHER", grade, number)
    for grade, subject in sorted(leaders):
        add_filter_scope("SUBJECT_LEADER", grade, subject=subject)
    for grade in sorted(grade_values):
        add_filter_scope("GRADE_LEADER", grade)
    expanded_roles = {rule["role"] for rule in DEFAULT_RULES if rule["role"] != "TEACHER"}
    legacy = not teaching and not duties.intersection(expanded_roles)
    assignments = teacher.get("assignments") or []
    if legacy:
        subject_names = {subject["subject_id"]: subject["name"] for subject in config["subjects"]}
        for assignment in assignments:
            grade, number = assignment.get("grade", ""), assignment.get("class_number", "")
            name = assignment.get("subject", subject_names.get(assignment["subject_id"], ""))
            if grade and number:
                add_filter_scope("TEACHER", grade, number, name)
            else:
                for person in people.values():
                    if person.get("class_id") == assignment["class_id"]:
                        add_filter_scope("TEACHER", person["grade"], person["class_number"], name)

    matched_roles = []
    for rule in rules:
        role = rule["role"]
        role_subjects, role_classes = set(), set()
        for subject in config["subjects"]:
            name = normalized(subject["name"])
            for identifier in subject["student_ids"]:
                person = people.get(identifier)
                if person is None:
                    continue
                if role == "TEACHER":
                    matches = any(name == taught and class_matches(person, grade, number) for taught, grade, number in teaching)
                    if legacy:
                        matches = any(subject["subject_id"] == assignment["subject_id"]
                                      and (person.get("class_id") == assignment["class_id"] if person.get("class_id") else
                                           class_matches(person, assignment.get("grade", ""), assignment.get("class_number", "")))
                                      for assignment in assignments)
                elif role == "HOMEROOM_TEACHER":
                    matches = any(class_matches(person, grade, number) for grade, number in homerooms)
                elif role == "SUBJECT_LEADER":
                    matches = any(name == taught and grade_name(person["grade"]) == grade_name(grade) for grade, taught in leaders)
                elif role == "GRADE_LEADER":
                    matches = grade_name(person["grade"]) in grade_values
                else:
                    matches = True
                if matches:
                    role_subjects.add(subject["subject_id"])
                    role_classes.add(classes_by_student[identifier])
        # An unmatched duty must not contribute other subjects, classes or query types.
        if role_subjects and role_classes:
            subjects.update(role_subjects)
            classes.update(role_classes)
            types.update(rule["types"])
            matched_roles.append(rule["label"])
            has_grade_scope |= role in {"SUBJECT_LEADER", "GRADE_LEADER"}
            has_school_scope |= role in {"ACADEMIC_DIRECTOR", "PRINCIPAL", "GENERAL_DIRECTOR", "SCHOOL_VIEWER"}
    grades = {person["grade"] for identifier, person in people.items() if classes_by_student[identifier] in classes}
    full_grades = {classes_by_student[identifier] for identifier, person in people.items() if person["grade"] in grades}
    range_type = "all" if has_school_scope else "grade" if has_grade_scope and classes and classes == full_grades else "class"
    ordered_types = [value for value in DEFAULT_RULES[-1]["types"] if value in types]
    ordered_subjects = [subject["subject_id"] for subject in config["subjects"] if subject["subject_id"] in subjects]
    score_subjects = [identifier for identifier in ordered_subjects if identifier in ready]
    warnings = []
    if not classes:
        warnings.append("教师职责与本次考试的科目、参试班级没有有效交集，请核对档案或手动选择学生范围。")
    if not subjects:
        warnings.append("没有可按教师职责预选的考试科目，请手动选择查询类型与科目。")
    return {"duties": sorted(duties), "role_labels": [rule["label"] for rule in rules],
            "filter_scopes": filter_scopes, "matched_roles": matched_roles,
            "scope_classes": sorted(classes), "scope_grades": sorted(grades), "scope_subject_ids": ordered_subjects,
            "default_warnings": warnings,
            "recommendation": {"teacher_id": teacher["id"], "score_types": ordered_types if score_subjects else [],
                "score_subjects": score_subjects, "diagnosis_types": ordered_types if ordered_subjects else [],
                "diagnosis_subjects": ordered_subjects, "essay_types": [], "range_type": range_type,
                "grades": sorted(grades) if range_type == "grade" else [], "classes": sorted(classes) if range_type == "class" else []}}
