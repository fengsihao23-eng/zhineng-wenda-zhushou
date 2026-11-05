"""Administrator audit events never contain credentials or request bodies."""
from ipaddress import ip_address

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.trace import AuditLog

ADMIN_ROLES = {"SUPER_ADMIN", "SCHOOL_ADMIN", "CITY_OPERATOR", "EXAM_ADMIN", "QA", "SCHOOL_VIEWER"}


def request_metadata(request):
    # Use the actual peer, not an arbitrary client-supplied forwarding header.
    host = request.client.host if request.client else None
    try:
        host = str(ip_address(host)) if host else None
    except ValueError:
        host = None
    return {
        "ip_address": host,
        "user_agent": request.headers.get("user-agent", "")[:500],
        "request_id": getattr(request.state, "request_id", None),
    }


def event(db, request, actor_id, action, item, school_id, *, extra=None, allowed=True):
    db.add(AuditLog(
        action=f"administrator.{action}", actor_type="user", actor_id=actor_id,
        resource_type=item.__tablename__, resource_id=item.id, allowed=allowed,
        extra_data={"school_id": str(school_id) if school_id else None, **(extra or {})},
        **request_metadata(request),
    ))


def bind_request(request, db, user, roles):
    if user.administrator_code or ADMIN_ROLES.intersection(roles):
        request.state.administrator_audit = {
            "actor_id": user.id, "school_id": str(user.school_id) if user.school_id else None,
            "username": user.username, "roles": list(roles),
            "factory": async_sessionmaker(db.bind, expire_on_commit=False),
        }


async def record_request(request, status_code):
    context = getattr(request.state, "administrator_audit", None)
    if not context:
        return
    route = request.scope.get("route")
    # The route template excludes free-form path/query data and credentials.
    route_path = getattr(route, "path", request.url.path)[:250]
    # Avoid adding an event merely for reading this event list: otherwise each
    # page read shifts offset pagination. Denied history access is still logged.
    if request.method == "GET" and route_path == "/api/v1/platform/administrators/history" and status_code < 400:
        return
    async with context["factory"]() as db:
        db.add(AuditLog(
            action="administrator.request", actor_type="user", actor_id=context["actor_id"],
            resource_type="http_request", allowed=status_code < 400,
            extra_data={
                "school_id": context["school_id"], "username": context["username"],
                "roles": context["roles"], "method": request.method,
                "route": route_path, "status_code": status_code,
                "resource_ids": {key: str(value)[:100] for key, value in request.path_params.items()},
            },
            **request_metadata(request),
        ))
        await db.commit()
