"""Public landing + self-service club registration."""
import re
import unicodedata

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import ADMIN_COOKIE, hash_password, make_token
from app.api.templating import templates
from app.db.engine import get_db
from app.db.models import Club

router = APIRouter()

TIMEZONES = [
    ("America/Santiago", "Chile"),
    ("America/Argentina/Buenos_Aires", "Argentina"),
    ("America/Lima", "Perú"),
    ("America/Bogota", "Colombia"),
    ("America/Guayaquil", "Ecuador"),
    ("America/La_Paz", "Bolivia"),
    ("America/Asuncion", "Paraguay"),
    ("America/Montevideo", "Uruguay"),
    ("America/Mexico_City", "México"),
]


def slugify(nombre: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", sin_acentos.lower()).strip("-")
    return slug[:50] or "club"


async def _slug_unico(db: AsyncSession, base: str) -> str:
    slug, n = base, 1
    while (await db.execute(select(Club.id).where(Club.slug == slug))).scalar_one_or_none():
        n += 1
        slug = f"{base}-{n}"
    return slug


@router.get("/")
async def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html", {})


@router.get("/privacidad")
async def privacidad(request: Request):
    return templates.TemplateResponse(request, "privacidad.html", {})


@router.get("/terminos")
async def terminos(request: Request):
    return templates.TemplateResponse(request, "terminos.html", {})


@router.get("/registro")
async def registro_page(request: Request):
    return templates.TemplateResponse(request, "registro.html", {
        "error": None, "timezones": TIMEZONES, "valores": {},
    })


@router.post("/registro")
async def registrar_club(
    request: Request,
    nombre: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    timezone: str = Form("America/Santiago"),
    db: AsyncSession = Depends(get_db),
):
    nombre, email = nombre.strip(), email.strip().lower()
    valores = {"nombre": nombre, "email": email, "timezone": timezone}

    def error(msg: str):
        return templates.TemplateResponse(request, "registro.html", {
            "error": msg, "timezones": TIMEZONES, "valores": valores,
        })

    if len(nombre) < 3:
        return error("El nombre del club es muy corto.")
    if len(password) < 8:
        return error("La contraseña debe tener al menos 8 caracteres.")
    if timezone not in {tz for tz, _ in TIMEZONES}:
        return error("Zona horaria inválida.")

    existe = (await db.execute(select(Club.id).where(Club.email == email))).scalar_one_or_none()
    if existe:
        return error("Ya existe un club registrado con ese email. ¿Quieres iniciar sesión?")

    club = Club(
        nombre=nombre,
        slug=await _slug_unico(db, slugify(nombre)),
        timezone=timezone,
        email=email,
        password_admin=hash_password(password),
        # El dashboard de staff parte con la misma clave; se puede cambiar después.
        password_dashboard=hash_password(password),
    )
    db.add(club)
    await db.commit()

    resp = RedirectResponse(f"/admin/{club.slug}", status_code=303)
    resp.set_cookie(ADMIN_COOKIE, make_token(f"club:{club.slug}"), httponly=True, max_age=60 * 60 * 12)
    return resp
