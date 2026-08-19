from pathlib import Path

from fastapi.templating import Jinja2Templates


def _auth_context(request) -> dict:
    # Imported lazily to avoid a circular import (auth → config only, but keeps modules decoupled)
    from app.api.auth import SUPER_SCOPE, admin_scope

    return {"es_super": admin_scope(request) == SUPER_SCOPE}


templates = Jinja2Templates(
    directory=Path(__file__).parents[1] / "templates",
    context_processors=[_auth_context],
)
