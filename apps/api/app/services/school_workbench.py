"""School roster, teaching grants and examinations; history is never deleted."""
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import load_only
from app.core.errors import ApiError
from app.core.access_scope import active_grants, is_teacher_only, scoped, scoped_scores
from app.db.models.import_batch import ImportedClass
from app.db.models.teaching import TeachingAssignment
from app.db.models.student import Student
from app.db.models.user import User, Role, UserRole
from app.db.models.exam import Exam, Subject, ExamSubject
from app.db.models.score import StudentSubjectScore, QuestionScore
from app.db.models.education import QuestionVersion, QuestionTag, TaxonomyNode, Question
from app.services.education_common import owned, data, claim, audit, native_only

MODELS = {
    "classes": ImportedClass,
    "students": Student,
    "subjects": Subject,
    "exams": Exam,
    "teaching": TeachingAssignment,
    "teachers": User,
}
FIELDS = {
    "teachers": ("id", "display_name", "status"),
    "classes": ("id", "name", "external_class_id", "source_system", "status"),
    "students": (
        "id",
        "name",
        "student_no",
        "external_student_id",
        "class_id",
        "external_class_id",
        "user_id",
        "source_system",
        "status",
    ),
    "subjects": ("id", "name", "code", "external_subject_id", "source_system"),
    "exams": (
        "id",
        "name",
        "external_exam_id",
        "exam_type",
        "start_date",
        "end_date",
        "status",
        "source_system",
    ),
    "teaching": (
        "id",
        "teacher_user_id",
        "class_id",
        "subject_id",
        "status",
        "starts_at",
        "expires_at",
    ),
}


async def listing(db, actor, kind, search="", page=1, page_size=30):
    model = MODELS[kind]
    query = select(model).where(model.school_id == actor.school_id)
    if kind == "teachers":
        if is_teacher_only(actor):
            raise ApiError(403, "ADMIN_REQUIRED", "教师账号维护仅限学校管理员。")
        query = query.options(
            load_only(User.id, User.school_id, User.display_name, User.status)
        ).where(
            User.status != "deleted",
            User.id.in_(
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(UserRole.school_id == actor.school_id, Role.code == "TEACHER")
            )
        )
        if search:
            query = query.where(User.display_name.contains(search, autoescape=True))
    if is_teacher_only(actor) and not (actor.has_role("EXAM_ADMIN") and kind in {"classes", "subjects", "exams"}):
        if kind == "teaching":
            query = query.where(*active_grants(actor))
        elif kind == "classes":
            query = query.where(
                model.id.in_(
                    select(TeachingAssignment.class_id).where(*active_grants(actor))
                )
            )
        elif kind == "subjects":
            query = query.where(
                model.id.in_(
                    select(TeachingAssignment.subject_id).where(*active_grants(actor))
                )
            )
        elif kind == "students":
            query = scoped(query, actor, model.school_id)
        else:
            query = query.where(
                model.id.in_(
                    scoped_scores(
                        select(StudentSubjectScore.exam_id), actor, StudentSubjectScore
                    )
                )
            )
    if search and hasattr(model, "name"):
        query = query.where(model.name.contains(search, autoescape=True))
    total = int(
        await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    )
    rows = (
        await db.scalars(
            query.order_by(model.id).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return {
        "items": [
            {
                **data(row, *FIELDS[kind]),
                **({"name": row.display_name} if kind == "teachers" else {}),
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def users(db, actor):
    rows = (
        await db.execute(
            select(User.id, User.display_name, Role.code)
            .join(
                UserRole,
                and_(UserRole.user_id == User.id, UserRole.school_id == User.school_id),
            )
            .join(Role, Role.id == UserRole.role_id)
            .where(
                User.school_id == actor.school_id,
                User.status == "active",
                Role.code.in_(["TEACHER", "STUDENT"]),
            )
            .order_by(User.id)
            .limit(500)
        )
    ).all()
    return [
        {"id": str(identifier), "name": name, "role": role}
        for identifier, name, role in rows
    ]


async def validate_teaching(db, actor, body):
    classroom = await owned(db, ImportedClass, body.class_id, actor)
    if classroom.status != "active" and body.status == "active":
        raise ApiError(422, "CLASS_INACTIVE", "停用班级不能授予有效任教权限。")
    await owned(db, Subject, body.subject_id, actor)
    teacher = await db.scalar(
        select(User.id)
        .join(
            UserRole,
            and_(UserRole.user_id == User.id, UserRole.school_id == User.school_id),
        )
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.id == body.teacher_user_id,
            User.school_id == actor.school_id,
            User.status == "active",
            Role.code == "TEACHER",
        )
    )
    if teacher is None:
        raise ApiError(422, "TEACHER_ACCOUNT_REQUIRED", "任教关系只能绑定本校有效教师账号。")


async def create(db, actor, kind, body, key):
    model = MODELS[kind]
    if kind == "teaching":
        await validate_teaching(db, actor, body)
    if kind == "students":
        classroom = await owned(db, ImportedClass, body.class_id, actor)
        if classroom.status != "active":
            raise ApiError(422, "CLASS_INACTIVE", "不能把学生加入停用班级。")
    identifier, fresh = await claim(
        db, actor, f"{kind}.create", key, body.model_dump(mode="json")
    )
    if fresh:
        values = body.model_dump()
        if kind != "teaching":
            values["source_system"] = "native"
        item = model(id=identifier, school_id=actor.school_id, **values)
        db.add(item)
        audit(db, actor, f"{kind}.create", item)
        await db.commit()
    return data(await owned(db, model, identifier, actor), *FIELDS[kind])


async def update_record(db, actor, kind, identifier, body):
    item = await owned(db, MODELS[kind], identifier, actor, lock=True)
    if kind != "teaching":
        native_only(item)
    if kind == "teaching":
        await validate_teaching(db, actor, body)
    if kind == "students":
        classroom = await owned(db, ImportedClass, body.class_id, actor)
        if classroom.status != "active" and body.status == "active":
            raise ApiError(422, "CLASS_INACTIVE", "不能加入停用班级。")
    if kind == "classes" and body.status == "inactive":
        active_students = await db.scalar(
            select(Student.id)
            .where(
                Student.school_id == actor.school_id,
                Student.status == "active",
                or_(
                    Student.class_id == item.id,
                    and_(
                        Student.class_id.is_(None),
                        Student.external_class_id == item.external_class_id,
                    ),
                ),
            )
            .limit(1)
        )
        active_teaching = await db.scalar(
            select(TeachingAssignment.id)
            .where(
                TeachingAssignment.school_id == actor.school_id,
                TeachingAssignment.class_id == item.id,
                TeachingAssignment.status == "active",
            )
            .limit(1)
        )
        if active_students or active_teaching:
            raise ApiError(409, "CLASS_REFERENCED", "请先调整在籍学生和有效任教关系，再停用班级；历史成绩会保留。")
    changed = any(getattr(item, k) != v for k, v in body.model_dump().items())
    if changed:
        for field, value in body.model_dump().items():
            setattr(item, field, value)
        audit(db, actor, f"{kind}.update", item)
        await db.commit()
    return data(item, *FIELDS[kind])


async def update_teacher(db, actor, identifier, body):
    teacher = await db.scalar(
        select(User)
        .options(load_only(User.id, User.school_id, User.display_name, User.status))
        .where(
            User.id == identifier,
            User.school_id == actor.school_id,
            User.id.in_(
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(UserRole.school_id == actor.school_id, Role.code == "TEACHER")
            ),
        )
        .with_for_update()
    )
    if teacher is None:
        raise ApiError(404, "TEACHER_NOT_AVAILABLE", "本校教师账号不存在。")
    if teacher.display_name != body.display_name or teacher.status != body.status:
        teacher.display_name, teacher.status = body.display_name, body.status
        audit(db, actor, "teacher.update", teacher)
        await db.commit()
    return {
        **data(teacher, "id", "display_name", "status"),
        "name": teacher.display_name,
    }


async def bind_student(db, actor, identifier, body):
    student = await owned(db, Student, identifier, actor, lock=True)
    user = await db.scalar(
        select(User.id)
        .join(
            UserRole,
            and_(UserRole.user_id == User.id, UserRole.school_id == User.school_id),
        )
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.id == body.user_id,
            User.school_id == actor.school_id,
            User.status == "active",
            Role.code == "STUDENT",
        )
        .with_for_update(of=User)
    )
    if user is None:
        raise ApiError(422, "STUDENT_ACCOUNT_REQUIRED", "请选择本校有效学生账号。")
    occupied = await db.scalar(
        select(Student.id).where(
            Student.school_id == actor.school_id,
            Student.user_id == body.user_id,
            Student.id != identifier,
        )
    )
    if occupied or (student.user_id and student.user_id != body.user_id):
        raise ApiError(409, "ACCOUNT_BINDING_CONFLICT", "账号已有绑定，请通过身份核查流程处理，不能直接覆盖。")
    if student.user_id != body.user_id:
        student.user_id = body.user_id
        audit(db, actor, "student.bind", student)
        await db.commit()
    return data(student, *FIELDS["students"])


async def exam_detail(db, actor, identifier):
    exam = await owned(db, Exam, identifier, actor)
    rows = (
        await db.execute(
            select(ExamSubject, Subject)
            .join(Subject, Subject.id == ExamSubject.subject_id)
            .where(
                ExamSubject.exam_id == identifier, Subject.school_id == actor.school_id
            )
        )
    ).all()
    return {
        **data(exam, *FIELDS["exams"]),
        "subjects": [
            {
                "subject_id": str(subject.id),
                "name": subject.name,
                "full_score": float(es.full_score),
            }
            for es, subject in rows
        ],
    }


async def set_exam_subject(db, actor, identifier, body):
    exam = await owned(db, Exam, identifier, actor, lock=True)
    native_only(exam)
    await owned(db, Subject, body.subject_id, actor)
    item = await db.scalar(
        select(ExamSubject).where(
            ExamSubject.exam_id == identifier, ExamSubject.subject_id == body.subject_id
        )
    )
    if item and float(item.full_score) != body.full_score:
        used = await db.scalar(
            select(StudentSubjectScore.id)
            .where(
                StudentSubjectScore.school_id == actor.school_id,
                StudentSubjectScore.exam_id == identifier,
                StudentSubjectScore.subject_id == body.subject_id,
            )
            .limit(1)
        )
        if used:
            raise ApiError(409, "EXAM_SUBJECT_REFERENCED", "已有成绩引用该满分，不能直接改变历史计算口径。")
    if item is None:
        item = ExamSubject(exam_id=identifier, **body.model_dump())
        db.add(item)
    else:
        item.full_score = body.full_score
    audit(db, actor, "exam.subject", exam)
    await db.commit()
    return await exam_detail(db, actor, identifier)


async def link_score(db, actor, identifier, body):
    score = await owned(db, QuestionScore, identifier, actor, lock=True)
    version = await owned(db, QuestionVersion, body.question_version_id, actor)
    question = await owned(db, Question, version.question_id, actor)
    if (
        not version.published_at
        or question.deleted_at
        or question.subject_id != score.subject_id
    ):
        raise ApiError(422, "QUESTION_VERSION_INVALID", "只能关联同学科的正式题目版本。")
    if score.question_version_id and score.question_version_id != version.id:
        raise ApiError(409, "SCORE_ALREADY_LINKED", "得分依据已固定，不能覆盖历史题目版本。")
    if score.question_version_id != version.id:
        score.question_version_id, score.question_id = version.id, question.id
        audit(db, actor, "score.link", score, {"question_version_id": str(version.id)})
        await db.commit()
    return data(score, "id", "question_id", "question_version_id")


async def class_analysis(db, actor, class_id, subject_id, exam_id):
    classroom = await owned(db, ImportedClass, class_id, actor)
    await owned(db, Subject, subject_id, actor)
    await owned(db, Exam, exam_id, actor)
    if is_teacher_only(actor) and not await db.scalar(
        select(TeachingAssignment.id).where(
            *active_grants(actor),
            TeachingAssignment.class_id == class_id,
            TeachingAssignment.subject_id == subject_id,
        )
    ):
        raise ApiError(404, "CLASS_NOT_AVAILABLE", "该班级学科不在任教范围内。")
    in_class = or_(
        Student.class_id == class_id,
        and_(
            Student.class_id.is_(None),
            Student.external_class_id == classroom.external_class_id,
        ),
    )
    base = (
        select(StudentSubjectScore)
        .join(Student, Student.id == StudentSubjectScore.student_id)
        .where(
            StudentSubjectScore.school_id == actor.school_id,
            Student.school_id == actor.school_id,
            in_class,
            StudentSubjectScore.subject_id == subject_id,
            StudentSubjectScore.exam_id == exam_id,
        )
    )
    scores = (await db.scalars(base)).all()
    values = [float(s.score) for s in scores]
    distribution = [
        {"label": "低于 60%", "count": 0},
        {"label": "60%–80%", "count": 0},
        {"label": "80% 及以上", "count": 0},
        {"label": "满分未知", "count": 0},
    ]
    for score in scores:
        rate = (
            float(score.score) / float(score.full_score)
            if score.full_score and score.full_score > 0
            else None
        )
        bucket = 3 if rate is None else 0 if rate < 0.6 else 1 if rate < 0.8 else 2
        distribution[bucket]["count"] += 1
    selected_exam = await owned(db, Exam, exam_id, actor)
    previous = None
    if selected_exam.start_date:
        prior_exam = await db.scalar(
            select(Exam)
            .join(StudentSubjectScore, StudentSubjectScore.exam_id == Exam.id)
            .join(Student, Student.id == StudentSubjectScore.student_id)
            .where(
                Exam.school_id == actor.school_id,
                StudentSubjectScore.school_id == actor.school_id,
                Student.school_id == actor.school_id,
                in_class,
                StudentSubjectScore.subject_id == subject_id,
                Exam.start_date < selected_exam.start_date,
            )
            .order_by(Exam.start_date.desc())
            .limit(1)
        )
        if prior_exam:
            prior_scores = (
                await db.scalars(
                    select(StudentSubjectScore)
                    .join(Student, Student.id == StudentSubjectScore.student_id)
                    .where(
                        StudentSubjectScore.school_id == actor.school_id,
                        Student.school_id == actor.school_id,
                        in_class,
                        StudentSubjectScore.subject_id == subject_id,
                        StudentSubjectScore.exam_id == prior_exam.id,
                    )
                )
            ).all()
            average = sum(float(s.score) for s in prior_scores) / len(prior_scores)
            full_scores = {
                float(s.full_score)
                for s in [*scores, *prior_scores]
                if s.full_score and s.full_score > 0
            }
            comparable = len(full_scores) == 1 and all(
                s.full_score and s.full_score > 0 for s in [*scores, *prior_scores]
            )
            previous = {
                "exam": prior_exam.name,
                "sample_size": len(prior_scores),
                "average": round(average, 2),
                "average_delta": round(sum(values) / len(values) - average, 2)
                if values and comparable
                else None,
                "comparable_full_score": comparable,
            }
    losses = (
        await db.execute(
            select(QuestionScore, TaxonomyNode.name)
            .join(Student, Student.id == QuestionScore.student_id)
            .outerjoin(
                TaxonomyNode,
                and_(
                    TaxonomyNode.id == QuestionScore.knowledge_point_id,
                    TaxonomyNode.school_id == actor.school_id,
                ),
            )
            .where(
                QuestionScore.school_id == actor.school_id,
                Student.school_id == actor.school_id,
                in_class,
                QuestionScore.exam_id == exam_id,
                QuestionScore.subject_id == subject_id,
            )
        )
    ).all()
    points, unknown = {}, 0
    for score, name in losses:
        tags = []
        if not name and score.question_version_id:
            tags = (
                await db.scalars(
                    select(TaxonomyNode.name)
                    .join(QuestionTag, QuestionTag.node_id == TaxonomyNode.id)
                    .where(
                        QuestionTag.question_version_id == score.question_version_id,
                        TaxonomyNode.kind == "knowledge",
                        TaxonomyNode.school_id == actor.school_id,
                    )
                )
            ).all()
        names = [name] if name else tags
        if not names:
            unknown += 1
        for label in names:
            point = points.setdefault(
                label, {"lost_score": 0, "questions": 0, "students": set()}
            )
            point["lost_score"] += float(score.lost_score)
            point["questions"] += 1
            point["students"].add(str(score.student_id))
    audit(
        db,
        actor,
        "class.analysis",
        classroom,
        {"exam_id": str(exam_id), "subject_id": str(subject_id)},
    )
    await db.commit()
    return {
        "class_name": classroom.name,
        "sample_size": len(values),
        "average": round(sum(values) / len(values), 2) if values else None,
        "distribution": distribution,
        "previous_exam": previous,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "students": [
            {
                "student_id": str(s.student_id),
                "label": f"学生 {index+1}",
                "score": float(s.score),
                "full_score": float(s.full_score),
            }
            for index, s in enumerate(scores)
        ],
        "knowledge_points": [
            {
                "name": name,
                "lost_score": round(v["lost_score"], 2),
                "question_count": v["questions"],
                "sample_size": len(v["students"]),
            }
            for name, v in points.items()
        ],
        "unmapped_question_count": unknown,
        "note": "按当前班级归属统计；知识点多标签按各标签完整计入，不能相加作为总丢分。掌握状态不由分数推断。",
    }
