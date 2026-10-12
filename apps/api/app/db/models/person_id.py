"""Permanent platform identities, independent of mutable school/account fields."""
from uuid import uuid4
from sqlalchemy import BigInteger, Integer, Column, String, DateTime, Identity, CheckConstraint, UniqueConstraint, event, select, inspect
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.db.base import Base
from app.db.types import UUID

MIN_PERSON_ID = 10_000_001
MAX_PERSON_ID = 9_999_999_999


class PlatformPersonId(Base):
    __tablename__ = "platform_person_ids"
    id = Column(BigInteger().with_variant(Integer, "sqlite"),
                Identity(always=True, start=MIN_PERSON_ID, minvalue=MIN_PERSON_ID, maxvalue=MAX_PERSON_ID, cycle=False), primary_key=True)
    kind = Column(String(10), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    school_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # No FK to the person: even an erroneous import's deleted ID remains reserved.
    __table_args__ = (
        UniqueConstraint("kind", "entity_id", name="uq_platform_person_entity"),
        UniqueConstraint("school_id", "entity_id", "id", name="uq_platform_person_binding"),
        CheckConstraint("id BETWEEN 10000001 AND 9999999999", name="person_id_range"),
        CheckConstraint("kind IN ('student', 'teacher')", name="person_id_kind"),
        {"sqlite_autoincrement": True},
    )


@event.listens_for(PlatformPersonId.__table__, "after_create")
def _sqlite_sequence(table, connection, **kwargs):
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("INSERT INTO sqlite_sequence(name, seq) VALUES ('platform_person_ids', 10000000)")


def _allocate(connection, kind, entity_id, school_id):
    """The database assigns numbers atomically; never derive one from row counts."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    table = PlatformPersonId.__table__
    insert = pg_insert if connection.dialect.name == "postgresql" else sqlite_insert
    number = connection.scalar(insert(table).values(kind=kind, entity_id=entity_id, school_id=school_id).on_conflict_do_nothing(
        index_elements=["kind", "entity_id"]).returning(table.c.id))
    if number is None:
        number = connection.scalar(select(table.c.id).where(table.c.kind == kind, table.c.entity_id == entity_id, table.c.school_id == school_id))
    if number is None:
        raise ValueError("Platform identity belongs to another school")
    return number


@event.listens_for(Session, "before_flush")
def _assign_person_ids(session, flush_context, instances):
    # Covers roster Excel, legacy score/CSV intake and administrative creation.
    # AsyncSession runs this through its adapted synchronous connection.
    from app.db.models.student import Student
    from app.db.models.user import User, Role, UserRole
    from app.db.models.roster import TeacherProfile, TeacherDeletion
    for obj in session.dirty:
        if isinstance(obj, (Student, User, TeacherDeletion)):
            history = inspect(obj).attrs.platform_id.history
            if history.deleted and history.deleted[0] is not None and history.has_changes():
                raise ValueError("Platform person ID cannot be changed")
    pending = list(session.new)
    teachers = {}
    for obj in pending:
        if isinstance(obj, (Student, User)) and obj.id is None:
            obj.id = uuid4()
        if isinstance(obj, User):
            teachers[obj.id] = obj
    targets = [("student", obj) for obj in pending if isinstance(obj, Student)]
    teacher_ids = {obj.id for obj in pending + list(session.dirty) if isinstance(obj, User) and obj.account_type == "teacher" and obj.platform_id is None}
    teacher_ids.update(obj.id for obj in pending if isinstance(obj, TeacherProfile))
    teacher_ids.update(obj.user_id for obj in pending if isinstance(obj, TeacherDeletion))
    grants = [obj for obj in pending if isinstance(obj, UserRole)]
    if not targets and not teacher_ids and not grants:
        return
    connection = session.connection()
    if grants:
        roles = {obj.id for obj in pending if isinstance(obj, Role) and obj.code == "TEACHER"}
        roles.update(connection.scalars(select(Role.id).where(Role.code == "TEACHER", Role.id.in_([obj.role_id for obj in grants]))))
        teacher_ids.update(obj.user_id for obj in grants if obj.role_id in roles)
    for identifier in teacher_ids:
        user = teachers.get(identifier) or session.get(User, identifier)
        if user is None:
            raise ValueError("Teacher identity requires an existing user")
        targets.append(("teacher", user))
    for kind, obj in targets:
        if obj.platform_id is None:
            obj.platform_id = _allocate(connection, kind, obj.id, obj.school_id)
    for obj in pending:
        if isinstance(obj, TeacherDeletion):
            user = teachers.get(obj.user_id) or session.get(User, obj.user_id)
            obj.platform_id = user.platform_id
