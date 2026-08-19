import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.engine import Base, get_db
from app.db import models  # noqa: F401
from app.main import app

TEST_DATABASE_URL = "postgresql+asyncpg://saidtrainer@localhost:5432/assist_tracker_test"


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Engine created inside the session event loop so asyncpg connections bind to it."""
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture(autouse=True)
def reset_messaging(monkeypatch):
    """Clear FakeProvider state between tests and disable retry sleeps."""
    from app.messaging import get_provider
    from app.services import alertas as alertas_svc

    monkeypatch.setattr(alertas_svc, "RETRY_DELAYS", [0, 0])
    provider = get_provider()
    if hasattr(provider, "sent"):
        provider.sent.clear()
        provider.fail_times = 0
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_db(engine):
    """Delete all rows after each test (reverse FK order)."""
    yield
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncClient:
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seed_data(db: AsyncSession):
    from app.db.models import Club, Categoria, Jugador, Staff

    import hashlib
    club = Club(
        nombre="Test Club", slug="test-club",
        email="club@test.cl",
        password_admin=hashlib.sha256(b"clubpass123").hexdigest(),
        password_dashboard=hashlib.sha256(b"test123").hexdigest(),
    )
    db.add(club)
    await db.commit()
    await db.refresh(club)

    cat = Categoria(
        club_id=club.id,
        nombre="Sub-13",
        hora_inicio="16:00",
        hora_fin="17:30",
        dias_entrenamiento=[1, 3, 5],
        min_checkins_semaforo=2,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)

    jugadores = [
        Jugador(categoria_id=cat.id, nombre="Juan", apellido="Pérez"),
        Jugador(categoria_id=cat.id, nombre="Pedro", apellido="González"),
        Jugador(categoria_id=cat.id, nombre="Luis", apellido="Muñoz"),
    ]
    db.add_all(jugadores)
    staff = Staff(club_id=club.id, nombre="DT Test", telefono_whatsapp="56912345678", rol="DT")
    db.add(staff)
    await db.commit()
    for j in jugadores:
        await db.refresh(j)

    return {"club": club, "categoria": cat, "jugadores": jugadores, "staff": staff}
