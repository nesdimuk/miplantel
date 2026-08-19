"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mp_clubes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(60), nullable=False, unique=True),
        sa.Column("timezone", sa.String(60), nullable=False, server_default="America/Santiago"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_clubes_slug", "mp_clubes", ["slug"])

    op.create_table(
        "mp_categorias",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("mp_clubes.id"), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("hora_inicio", sa.String(5), nullable=False),
        sa.Column("hora_fin", sa.String(5), nullable=False),
        sa.Column("dias_entrenamiento", postgresql.ARRAY(sa.Integer()), nullable=False, server_default="{1,2,3,4,5}"),
        sa.Column("min_checkins_semaforo", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("umbral_alerta_carga", sa.Integer(), nullable=False, server_default="800"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_categorias_club_id", "mp_categorias", ["club_id"])

    op.create_table(
        "mp_staff",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("mp_clubes.id"), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("telefono_whatsapp", sa.String(20), nullable=False),
        sa.Column("rol", sa.String(20), nullable=False),
        sa.Column("recibe_alertas", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("recibe_resumen", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_staff_club_id", "mp_staff", ["club_id"])

    op.create_table(
        "mp_jugadores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("categoria_id", sa.Integer(), sa.ForeignKey("mp_categorias.id"), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("apellido", sa.String(80), nullable=False),
        sa.Column("fecha_nacimiento", sa.Date(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_jugadores_categoria_id", "mp_jugadores", ["categoria_id"])

    op.create_table(
        "mp_checkins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jugador_id", sa.Integer(), sa.ForeignKey("mp_jugadores.id"), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("asistencia", sa.Boolean(), nullable=False),
        sa.Column("motivo_inasistencia", sa.String(200), nullable=True),
        sa.Column("sueno", sa.Integer(), nullable=True),
        sa.Column("energia", sa.Integer(), nullable=True),
        sa.Column("animo", sa.Integer(), nullable=True),
        sa.Column("dolor_pre", sa.Integer(), nullable=True),
        sa.Column("molestia_previa", sa.Boolean(), nullable=True),
        sa.Column("molestia_zona", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("jugador_id", "fecha", name="mp_uq_checkin_jugador_fecha"),
    )
    op.create_index("ix_checkins_jugador_fecha", "mp_checkins", ["jugador_id", "fecha"])

    op.create_table(
        "mp_checkouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jugador_id", sa.Integer(), sa.ForeignKey("mp_jugadores.id"), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("rpe", sa.Integer(), nullable=False),
        sa.Column("duracion_min", sa.Integer(), nullable=False),
        sa.Column("carga", sa.Integer(), nullable=False),
        sa.Column("fisico_post", sa.Integer(), nullable=True),
        sa.Column("rendimiento", sa.Integer(), nullable=True),
        sa.Column("molestia_nueva", sa.Boolean(), nullable=True),
        sa.Column("molestia_zona", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("jugador_id", "fecha", name="mp_uq_checkout_jugador_fecha"),
    )
    op.create_index("ix_checkouts_jugador_fecha", "mp_checkouts", ["jugador_id", "fecha"])

    op.create_table(
        "mp_sesiones_dia",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("categoria_id", sa.Integer(), sa.ForeignKey("mp_categorias.id"), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("total_checkins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_checkouts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("semaforo_enviado", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("felicitacion_mostrada", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("resumen_enviado", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("categoria_id", "fecha", name="mp_uq_sesion_categoria_fecha"),
    )
    op.create_index("ix_sesiones_categoria_fecha", "mp_sesiones_dia", ["categoria_id", "fecha"])

    op.create_table(
        "mp_alertas_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tipo", sa.String(50), nullable=False),
        sa.Column("categoria_id", sa.Integer(), sa.ForeignKey("mp_categorias.id"), nullable=True),
        sa.Column("jugador_id", sa.Integer(), sa.ForeignKey("mp_jugadores.id"), nullable=True),
        sa.Column("destinatario", sa.String(30), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column("estado_envio", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("respuesta_api", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_mp_alertas_categoria_id", "mp_alertas_log", ["categoria_id"])


def downgrade() -> None:
    op.drop_table("mp_alertas_log")
    op.drop_table("mp_sesiones_dia")
    op.drop_table("mp_checkouts")
    op.drop_table("mp_checkins")
    op.drop_table("mp_jugadores")
    op.drop_table("mp_staff")
    op.drop_table("mp_categorias")
    op.drop_table("mp_clubes")
