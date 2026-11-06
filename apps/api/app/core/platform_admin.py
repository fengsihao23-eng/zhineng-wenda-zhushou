"""Platform administrators govern accounts; school identities own business access."""
from app.core.errors import ApiError

GOVERNANCE_PATH = "/api/v1/platform/administrators"
PLATFORM_SELF_PATHS = {"/api/v1/auth/me", "/api/v1/auth/change-password"}


def enforce_platform_admin_route(request, roles):
    if "SUPER_ADMIN" not in {role.upper() for role in roles}:
        return
    path = request.url.path.rstrip("/")
    if path in PLATFORM_SELF_PATHS or path == GOVERNANCE_PATH or path.startswith(GOVERNANCE_PATH + "/"):
        return
    raise ApiError(403, "PLATFORM_ADMIN_GOVERNANCE_ONLY",
                   "超级管理员仅管理管理员账号和权限，学校业务请使用学校管理员账号。")
