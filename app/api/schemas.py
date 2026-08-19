from __future__ import annotations
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class CheckinCreate(BaseModel):
    jugador_id: int
    fecha: date
    asistencia: bool
    motivo_inasistencia: Optional[str] = Field(None, max_length=200)
    # Required only when asistencia=True
    sueno: Optional[int] = Field(None, ge=1, le=7)
    energia: Optional[int] = Field(None, ge=1, le=7)
    animo: Optional[int] = Field(None, ge=1, le=7)
    dolor_pre: Optional[int] = Field(None, ge=1, le=7)
    alimentacion: Optional[int] = Field(None, ge=1, le=7)
    molestia_previa: Optional[bool] = None
    molestia_zona: Optional[str] = Field(None, max_length=100)
    molestia_severidad: Optional[str] = Field(None, pattern="^(leve|limitante|bloqueante)$")

    @model_validator(mode="after")
    def validate_asistencia_fields(self) -> CheckinCreate:
        if self.asistencia:
            missing = [f for f in ("sueno", "energia", "animo", "dolor_pre", "alimentacion") if getattr(self, f) is None]
            if missing:
                raise ValueError(f"Campos requeridos cuando asistencia=True: {missing}")
        else:
            if not self.motivo_inasistencia:
                raise ValueError("motivo_inasistencia es requerido cuando asistencia=False")
        return self


class CheckinResponse(BaseModel):
    id: int
    jugador_id: int
    fecha: date
    asistencia: bool
    feedback: Optional[str] = None  # gamified message shown on screen

    class Config:
        from_attributes = True


class CheckoutCreate(BaseModel):
    jugador_id: int
    fecha: date
    rpe: int = Field(..., ge=0, le=10)
    duracion_min: Optional[int] = Field(None, ge=1, le=300)  # None = derive from categoria config
    fisico_post: Optional[int] = Field(None, ge=1, le=7)
    rendimiento: Optional[int] = Field(None, ge=1, le=7)
    molestia_nueva: Optional[bool] = None
    molestia_zona: Optional[str] = Field(None, max_length=100)
    molestia_severidad: Optional[str] = Field(None, pattern="^(leve|limitante|bloqueante)$")


class CheckoutResponse(BaseModel):
    id: int
    jugador_id: int
    fecha: date
    rpe: int
    duracion_min: int
    carga: int

    class Config:
        from_attributes = True


class JugadorPublico(BaseModel):
    id: int
    nombre: str
    apellido: str

    class Config:
        from_attributes = True
