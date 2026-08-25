from __future__ import annotations
from datetime import date, datetime
from typing import Optional
from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, func, ARRAY,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.engine import Base


class Club(Base):
    __tablename__ = "mp_clubes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(60), default="America/Santiago")
    email: Mapped[Optional[str]] = mapped_column(String(120), unique=True, nullable=True, index=True)
    password_admin: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)      # sha256 hex
    password_dashboard: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # sha256 hex
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    color_primario: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)   # hex #RRGGBB
    color_secundario: Mapped[Optional[str]] = mapped_column(String(7), nullable=True) # hex #RRGGBB

    categorias: Mapped[list[Categoria]] = relationship(back_populates="club")
    staff: Mapped[list[Staff]] = relationship(back_populates="club")


class Categoria(Base):
    __tablename__ = "mp_categorias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("mp_clubes.id"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    hora_inicio: Mapped[str] = mapped_column(String(5), nullable=False)  # "HH:MM"
    horario_confirmado: Mapped[bool] = mapped_column(Boolean, default=False)
    hora_fin: Mapped[str] = mapped_column(String(5), nullable=False)
    hora_resumen: Mapped[str] = mapped_column(String(5), default="19:00")
    dias_entrenamiento: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=[0, 1, 2, 3, 4])  # 0=lunes … 6=domingo
    min_checkins_semaforo: Mapped[int] = mapped_column(Integer, default=10)
    # Puntos RPE×min por semana. Referencia: 4 sesiones × 120 min × RPE 6 ≈ 2.880;
    # un default bajo hace que "carga alta" dispare para todo el plantel y mate la señal.
    umbral_alerta_carga: Mapped[int] = mapped_column(Integer, default=3500)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    club: Mapped[Club] = relationship(back_populates="categorias")
    jugadores: Mapped[list[Jugador]] = relationship(back_populates="categoria")
    sesiones: Mapped[list[SesionDia]] = relationship(back_populates="categoria")
    alertas: Mapped[list[AlertaLog]] = relationship(back_populates="categoria")


class Jugador(Base):
    __tablename__ = "mp_jugadores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("mp_categorias.id"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False)
    apellido: Mapped[str] = mapped_column(String(80), nullable=False)
    fecha_nacimiento: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    categoria: Mapped[Categoria] = relationship(back_populates="jugadores")
    checkins: Mapped[list[Checkin]] = relationship(back_populates="jugador")
    checkouts: Mapped[list[Checkout]] = relationship(back_populates="jugador")


class Staff(Base):
    __tablename__ = "mp_staff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("mp_clubes.id"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    telefono_whatsapp: Mapped[str] = mapped_column(String(20), nullable=False)
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    rol: Mapped[str] = mapped_column(String(20), nullable=False)  # DT / PF / ADMIN / COORD
    recibe_alertas: Mapped[bool] = mapped_column(Boolean, default=True)
    recibe_resumen: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # null = recibe alertas de todas las categorías del club
    categoria_ids: Mapped[Optional[list[int]]] = mapped_column(ARRAY(Integer), nullable=True)
    es_coordinador: Mapped[bool] = mapped_column(Boolean, default=False)
    password_coord: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    club: Mapped[Club] = relationship(back_populates="staff")


class Checkin(Base):
    __tablename__ = "mp_checkins"
    __table_args__ = (UniqueConstraint("jugador_id", "fecha", name="mp_uq_checkin_jugador_fecha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jugador_id: Mapped[int] = mapped_column(ForeignKey("mp_jugadores.id"), nullable=False, index=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    asistencia: Mapped[bool] = mapped_column(Boolean, nullable=False)
    motivo_inasistencia: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    sueno: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)      # 1-7
    energia: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)    # 1-7
    animo: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)      # 1-7
    dolor_pre: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)    # 1-7
    alimentacion: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)       # 1-7 (solo nutricionista)
    estres: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)            # 1-7 Hooper
    hora_inicio_declarada: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)  # HH:MM
    molestia_previa: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    molestia_zona: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    molestia_severidad: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # leve|limitante|bloqueante
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    jugador: Mapped[Jugador] = relationship(back_populates="checkins")


class Checkout(Base):
    __tablename__ = "mp_checkouts"
    __table_args__ = (UniqueConstraint("jugador_id", "fecha", name="mp_uq_checkout_jugador_fecha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jugador_id: Mapped[int] = mapped_column(ForeignKey("mp_jugadores.id"), nullable=False, index=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    rpe: Mapped[int] = mapped_column(Integer, nullable=False)            # 0-10 Borg
    duracion_min: Mapped[int] = mapped_column(Integer, nullable=False)
    carga: Mapped[int] = mapped_column(Integer, nullable=False)          # rpe * duracion_min
    fisico_post: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # 1-7
    rendimiento: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # 1-7
    hora_termino: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)   # HH:MM declarado por el jugador
    molestia_nueva: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    molestia_zona: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    molestia_severidad: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # leve|limitante|bloqueante
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    jugador: Mapped[Jugador] = relationship(back_populates="checkouts")


class SesionDia(Base):
    __tablename__ = "mp_sesiones_dia"
    __table_args__ = (UniqueConstraint("categoria_id", "fecha", name="mp_uq_sesion_categoria_fecha"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("mp_categorias.id"), nullable=False, index=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    total_checkins: Mapped[int] = mapped_column(Integer, default=0)
    total_checkouts: Mapped[int] = mapped_column(Integer, default=0)
    semaforo_enviado: Mapped[bool] = mapped_column(Boolean, default=False)
    felicitacion_mostrada: Mapped[bool] = mapped_column(Boolean, default=False)
    resumen_enviado: Mapped[bool] = mapped_column(Boolean, default=False)
    primer_aviso_enviado: Mapped[bool] = mapped_column(Boolean, default=False)
    tercer_checkout_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resumen_post_enviado: Mapped[bool] = mapped_column(Boolean, default=False)
    dashboard_enviado: Mapped[bool] = mapped_column(Boolean, default=False)

    categoria: Mapped[Categoria] = relationship(back_populates="sesiones")


class Recordatorio(Base):
    __tablename__ = "mp_recordatorios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("mp_categorias.id"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    hora: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)            # fixed HH:MM, or…
    minutos_antes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)     # …relative to hora_inicio
    condicion_min_checkins: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # send only if checkins < N
    mensaje: Mapped[str] = mapped_column(String(500), nullable=False)
    last_enviado: Mapped[Optional[date]] = mapped_column(Date, nullable=True)        # daily claim
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    categoria: Mapped[Categoria] = relationship()


class AlertaLog(Base):
    __tablename__ = "mp_alertas_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    categoria_id: Mapped[Optional[int]] = mapped_column(ForeignKey("mp_categorias.id"), nullable=True, index=True)
    jugador_id: Mapped[Optional[int]] = mapped_column(ForeignKey("mp_jugadores.id"), nullable=True)
    destinatario: Mapped[str] = mapped_column(String(30), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    estado_envio: Mapped[str] = mapped_column(String(20), default="pending")  # pending/sent/delivered/read/failed
    respuesta_api: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    wamid: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)  # Meta message id, for delivery status webhooks
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    categoria: Mapped[Optional[Categoria]] = relationship(back_populates="alertas")
