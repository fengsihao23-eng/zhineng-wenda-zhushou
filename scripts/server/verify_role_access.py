"""Read-only smoke checks inside the deployed API container; no identity changes."""
import asyncio
import json
from datetime import timedelta
from urllib.request import Request, urlopen
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.api.deps import AuthenticatedUser
from app.core.access_scope import is_handoff_handler, is_teacher_only, student_ids, teaching_handler
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, ensure_account_environment
from app.db.models import HumanHandoff, Role, Student, User, UserRole
from app.db.models.answer_workbench import AnswerTicket


def get(route, token):
    request = Request("http://nginx/api/v1" + route, headers={"Authorization": "Bearer " + token})
    with urlopen(request, timeout=45) as response:
        assert response.status == 200, route
        return json.load(response)


async def main():
    summary = {"read_only": True, "account_roles_and_password_flags_changed": False, "checks": []}
    async with AsyncSessionLocal() as db:
        people = {}
        rows = await db.execute(select(User, Role.code).join(UserRole, UserRole.user_id == User.id)
                                .join(Role, Role.id == UserRole.role_id)
                                .where(UserRole.school_id == User.school_id, User.status == "active"))
        for user, role in rows:
            entry = people.setdefault(user.id, {"user": user, "roles": []})
            entry["roles"].append(role)
        for kind in ["school_reader", "teacher_reader", "school_admin", "super_admin"]:
            selected = None
            for entry in people.values():
                user, roles = entry["user"], set(entry["roles"])
                matches = {
                    "school_reader": "SCHOOL_VIEWER" in roles and "TEACHER" not in roles
                                     and not roles.intersection({"SCHOOL_ADMIN", "SUPER_ADMIN", "CITY_OPERATOR"}),
                    "teacher_reader": {"SCHOOL_VIEWER", "TEACHER"} <= roles
                                      and not roles.intersection({"SCHOOL_ADMIN", "SUPER_ADMIN", "CITY_OPERATOR"}),
                    "school_admin": "SCHOOL_ADMIN" in roles and "SUPER_ADMIN" not in roles,
                    "super_admin": "SUPER_ADMIN" in roles,
                }
                if not matches[kind] or user.must_change_password:
                    continue
                try:
                    await ensure_account_environment(user, db)
                except HTTPException:
                    continue
                selected = entry
                break
            if selected is None:
                summary["checks"].append({"kind": kind, "eligible_live_account": False})
                continue
            user = selected["user"]
            actor = AuthenticatedUser(user.id, user.school_id, user.username, selected["roles"])
            # Short-lived signed tokens stay in this process; nothing is persisted or printed.
            token = create_access_token({"sub": str(user.id), "password_version": user.password_version},
                                        expires_delta=timedelta(minutes=3))
            assert get("/auth/me", token)["user_id"] == str(user.id)
            responses = {name: get("/platform/management/" + name, token)
                         for name in ["overview", "students", "feedback", "risks", "handoffs"]}
            record = {"kind": kind, "eligible_live_account": True, "management_gets": 5,
                      "student_count": len(responses["students"])}
            if kind in {"school_reader", "teacher_reader"}:
                for name in ["feedback", "risks"]:
                    assert all(not item["allowed_transitions"] for item in responses[name])
                expected = {str(sid) for sid in (await db.scalars(select(Student.id).where(
                    Student.school_id == user.school_id, Student.status == "active"))).all()}
                assert {item["id"] for item in responses["students"]} == expected
                handler = teaching_handler(actor)
                allowed = set(await db.scalars(student_ids(handler))) if is_teacher_only(handler) else None
                checked = 0
                for item in responses["handoffs"]:
                    if item.get("source") != "support":
                        continue
                    row = await db.get(HumanHandoff, UUID(item["id"]))
                    may_handle = is_handoff_handler(actor) and (allowed is None or row.student_id in allowed)
                    detail = get("/platform/education/handoffs/" + item["id"], token)
                    if not may_handle:
                        assert not item["allowed_transitions"] and not detail["can_reply"]
                    checked += 1
                tickets = get("/answer-workbench/tickets?management=true", token)
                permitted_users = set(await db.scalars(select(Student.user_id).where(
                    Student.id.in_(student_ids(handler))))) if is_teacher_only(handler) else None
                for ticket in tickets:
                    row = await db.get(AnswerTicket, UUID(ticket["id"]))
                    if not is_handoff_handler(actor) or permitted_users is not None and row.user_id not in permitted_users:
                        assert not ticket["canClaim"] and not ticket["canReply"]
                record.update(read_scope="school", readonly_controls_verified=True,
                              support_details_checked=checked, answer_tickets_checked=len(tickets))
            if responses["students"]:
                detail = get("/platform/management/students/" + responses["students"][0]["id"], token)
                assert detail["student"]["id"] == responses["students"][0]["id"]
                record["student_detail"] = "ok"
            summary["checks"].append(record)
        await db.rollback()
    print(json.dumps(summary, ensure_ascii=False))


asyncio.run(main())
