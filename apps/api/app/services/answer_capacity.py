"""Transactional account quota and multi-worker online-person counting."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, update, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.core.errors import ApiError
from app.db.models import User
from app.db.models.answer_workbench import AnswerDailyUsage, AnswerPresence

LIMIT = 100
LEASE_SECONDS = 90
SHANGHAI = ZoneInfo("Asia/Shanghai")


def now():
    return datetime.now(timezone.utc)


def day_at(instant=None):
    return (instant or now()).astimezone(SHANGHAI).date()


def insert_for(db):
    return pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert


async def quota(db, actor):
    day = day_at()
    used = await db.scalar(select(AnswerDailyUsage.used).where(
        AnswerDailyUsage.school_id == actor.school_id, AnswerDailyUsage.user_id == actor.user_id,
        AnswerDailyUsage.day == day)) or 0
    reset = datetime.combine(day + timedelta(days=1), datetime.min.time(), SHANGHAI)
    return {"limit": LIMIT, "used": used, "remaining": max(0, LIMIT-used),
            "date": day.isoformat(), "resetAt": reset.isoformat(), "timezone": "Asia/Shanghai"}


async def reserve(db, actor):
    """The guarded upsert locks across processes. Its transaction includes the answer.

    No commit here: an exception rolls back the receipt, reservation and conversation.
    Idempotency must be claimed by the caller before entering this function.
    """
    day = day_at()
    used = await db.scalar(insert_for(db)(AnswerDailyUsage).values(
        school_id=actor.school_id, user_id=actor.user_id, day=day, used=1,
    ).on_conflict_do_update(index_elements=["school_id", "user_id", "day"],
        set_={"used": AnswerDailyUsage.used+1}, where=AnswerDailyUsage.used < LIMIT,
    ).returning(AnswerDailyUsage.used))
    if used is None:
        raise ApiError(429, "DAILY_QUESTION_LIMIT", "今日提问次数已用完，明日 00:00 恢复。仍可查看报告或提交留言。",
                       details={"quota": await quota(db, actor)})
    return day


async def release(db, actor, day):
    await db.execute(update(AnswerDailyUsage).where(
        AnswerDailyUsage.school_id == actor.school_id, AnswerDailyUsage.user_id == actor.user_id,
        AnswerDailyUsage.day == day, AnswerDailyUsage.used > 0,
    ).values(used=AnswerDailyUsage.used-1))


def congestion(count):
    # The supplied prototype includes the 1000-person boundary in extreme.
    level = "extreme" if count >= 1000 else "busy" if count >= 500 else None
    return {"count": count, "level": level,
            "label": "极度拥堵" if level == "extreme" else "较为拥堵" if level else "",
            "message": "请耐心等待，避免重复提交" if level == "extreme" else "回复可能需要更长时间" if level else ""}


async def status(db, actor):
    count = await db.scalar(select(func.count(func.distinct(AnswerPresence.user_id))).join(
        User, (User.id == AnswerPresence.user_id) & (User.school_id == AnswerPresence.school_id)
    ).where(AnswerPresence.expires_at > now(), User.status == "active")) or 0
    return {"quota": await quota(db, actor), "traffic": congestion(count)}


async def presence(db, actor, client_id, present=True):
    instant = now()
    await db.execute(delete(AnswerPresence).where(AnswerPresence.expires_at <= instant))
    if present:
        expires = instant + timedelta(seconds=LEASE_SECONDS)
        await db.execute(insert_for(db)(AnswerPresence).values(school_id=actor.school_id,
            user_id=actor.user_id, client_id=client_id, expires_at=expires,
        ).on_conflict_do_update(index_elements=["school_id", "user_id", "client_id"],
                               set_={"expires_at": expires}))
    else:
        await db.execute(delete(AnswerPresence).where(AnswerPresence.school_id == actor.school_id,
            AnswerPresence.user_id == actor.user_id, AnswerPresence.client_id == client_id))
    await db.commit()
    return await status(db, actor)
