import hashlib
import hmac
from typing import Optional

from fastapi import HTTPException, Request

from app.config import settings

ADMIN_COOKIE = "assist_admin"
DASH_COOKIE = "assist_dash"  # value scoped per club slug

SUPER_SCOPE = "admin"  # global superadmin (nosotros); clubs get "club:{slug}"


def _sign(value: str) -> str:
    return hmac.new(settings.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()


def make_token(scope: str) -> str:
    return f"{scope}|{_sign(scope)}"


def check_token(raw: Optional[str], scope: str) -> bool:
    return token_scope(raw) == scope


def token_scope(raw: Optional[str]) -> Optional[str]:
    """Verified scope carried by a signed cookie, or None if missing/tampered."""
    if not raw or "|" not in raw:
        return None
    value, signature = raw.rsplit("|", 1)
    return value if hmac.compare_digest(signature, _sign(value)) else None


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def admin_scope(request: Request) -> Optional[str]:
    return token_scope(request.cookies.get(ADMIN_COOKIE))


async def require_admin(request: Request) -> None:
    """Dependency: superadmin sees everything; a club admin only its own slug."""
    scope = admin_scope(request)
    if scope == SUPER_SCOPE:
        return
    club_slug = request.path_params.get("club_slug")
    if scope and scope.startswith("club:"):
        if club_slug is None or scope == f"club:{club_slug}":
            return
        raise HTTPException(404, "Club no encontrado")  # no revelar existencia de otros clubes
    raise HTTPException(303, headers={"Location": "/admin/login"})


def require_dash(request: Request, club_slug: str) -> bool:
    return check_token(request.cookies.get(DASH_COOKIE), f"dash:{club_slug}")
