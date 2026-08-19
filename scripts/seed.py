"""Seed script: Coquimbo Unido pilot — 2 categorías, 54 jugadores ficticios, 3 staff."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import hashlib

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models import Club, Categoria, Jugador, Staff, Recordatorio
from app.config import settings

NOMBRES = [
    "Matías", "Sebastián", "Diego", "Nicolás", "Ignacio", "Felipe", "Andrés",
    "Rodrigo", "Tomás", "Cristóbal", "Alejandro", "Pablo", "Francisco", "Javier",
    "Camilo", "Carlos", "Martín", "Gabriel", "Vicente", "Maximiliano",
    "Emilio", "Joaquín", "Lucas", "Benjamín", "Fernando", "Agustín", "Danilo",
]
APELLIDOS = [
    "González", "Muñoz", "Rojas", "Díaz", "Pérez", "Soto", "Contreras",
    "Silva", "Martínez", "Sepúlveda", "Morales", "Torres", "Figueroa",
    "Flores", "Vásquez", "Castro", "Fuentes", "Herrera", "Medina", "Aguilera",
    "Gutiérrez", "Espinoza", "Vargas", "Navarro", "Ibáñez", "Pizarro", "Ramos",
]


async def seed() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        club = Club(
            nombre="Coquimbo Unido",
            slug="coquimbo-unido",
            timezone="America/Santiago",
            email="staff@coquimbounido.cl",
            password_admin=hashlib.sha256(b"coquimbo-admin-2026").hexdigest(),
            password_dashboard=hashlib.sha256(b"coquimbo2026").hexdigest(),
        )
        db.add(club)
        await db.flush()

        sub13 = Categoria(
            club_id=club.id,
            nombre="Sub-13",
            hora_inicio="16:00",
            hora_fin="17:30",
            hora_resumen="19:00",
            dias_entrenamiento=[0, 2, 4],  # lunes, miércoles, viernes (0=lunes)
            min_checkins_semaforo=8,
            umbral_alerta_carga=750,
        )
        sub14 = Categoria(
            club_id=club.id,
            nombre="Sub-14",
            hora_inicio="17:30",
            hora_fin="19:00",
            hora_resumen="19:30",
            dias_entrenamiento=[0, 2, 4],
            min_checkins_semaforo=10,
            umbral_alerta_carga=3500,
        )
        db.add_all([sub13, sub14])
        await db.flush()

        # 27 jugadores Sub-13, 27 jugadores Sub-14
        jugadores = []
        for i in range(27):
            jugadores.append(Jugador(
                categoria_id=sub13.id,
                nombre=NOMBRES[i % len(NOMBRES)],
                apellido=APELLIDOS[i % len(APELLIDOS)],
            ))
        for i in range(27):
            jugadores.append(Jugador(
                categoria_id=sub14.id,
                nombre=NOMBRES[(i + 5) % len(NOMBRES)],
                apellido=APELLIDOS[(i + 7) % len(APELLIDOS)],
            ))
        db.add_all(jugadores)

        staff = [
            Staff(club_id=club.id, nombre="Raúl Vargas", telefono_whatsapp="56912345678", rol="DT"),
            Staff(club_id=club.id, nombre="Marcelo Said", telefono_whatsapp="56998765432", rol="ADMIN"),
            Staff(club_id=club.id, nombre="Claudio Pizarro", telefono_whatsapp="56955556666", rol="PF"),
        ]
        db.add_all(staff)

        recordatorios = [
            Recordatorio(
                categoria_id=sub13.id,
                nombre="Pre-entreno: faltan check-ins",
                minutos_antes=30,
                condicion_min_checkins=8,
                mensaje="Faltan check-ins para el semáforo. Comparte el QR con el equipo.",
            ),
            Recordatorio(
                categoria_id=sub14.id,
                nombre="Pre-entreno: faltan check-ins",
                minutos_antes=30,
                condicion_min_checkins=10,
                mensaje="Faltan check-ins para el semáforo. Comparte el QR con el equipo.",
            ),
        ]
        db.add_all(recordatorios)

        await db.commit()
        print(f"✅ Seed completo: club={club.id}, sub13={sub13.id}, sub14={sub14.id}, jugadores=54, staff=3")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
