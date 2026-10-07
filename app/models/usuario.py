from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


RolUsuario = Literal["conductor", "administrador"]


class PerfilUsuarioBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    telefono: str | None = Field(default=None, max_length=30)
    rol: RolUsuario = "conductor"

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, valor: str) -> str:
        return " ".join(valor.strip().split())

    @field_validator("telefono")
    @classmethod
    def limpiar_telefono(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        limpio = valor.strip()
        return limpio or None


class CrearPerfilUsuario(PerfilUsuarioBase):
    # El rol enviado por el cliente no se usa para elevar privilegios.
    rol: Literal["conductor"] = "conductor"


class ActualizarPerfilUsuario(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=100)
    telefono: str | None = Field(default=None, max_length=30)

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return " ".join(valor.strip().split())


class UsuarioRespuesta(PerfilUsuarioBase):
    uid: str
    email: EmailStr | None = None
    activo: bool = True
    creado_en: datetime
    actualizado_en: datetime


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)
