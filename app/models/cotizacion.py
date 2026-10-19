import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.ruta import Coordenada


class SolicitudCotizacion(BaseModel):
    # Vehículo registrado. La placa será validada contra Firestore
    # y contra el UID obtenido del token de Firebase.
    placa_vehiculo: str = Field(
        ...,
        min_length=5,
        max_length=8,
        description="Placa del vehículo registrado por el conductor",
    )

    # Estos campos aportan contexto al frontend, pero el backend no debe
    # confiar en ellos para validar propiedad, categoría o rendimiento.
    tipo_vehiculo_registrado: str | None = Field(
        default=None,
        max_length=40,
    )

    tipo_carroceria: str | None = Field(
        default=None,
        max_length=40,
    )

    numero_ejes: int | None = Field(
        default=None,
        ge=2,
        le=9,
    )

    origen: Coordenada
    destino: Coordenada

    tipo_vehiculo: Literal[
        "carro",
        "camion",
    ] = "camion"

    tipo_combustible: Literal[
        "gasolina",
        "acpm",
    ] = "acpm"

    rendimiento_km_galon: float = Field(
        ...,
        gt=0,
        le=100,
        description=(
            "Rendimiento del vehículo en kilómetros por galón"
        ),
    )

    precio_combustible_galon: float = Field(
        ...,
        gt=0,
        description="Precio del combustible por galón",
    )

    numero_trayectos: int = Field(
        default=1,
        ge=1,
        le=2,
        description="1 para solo ida y 2 para ida y regreso",
    )

    categoria_peaje: Literal[
        "I",
        "II",
        "III",
        "IV",
        "V",
        "VI",
        "VII",
    ] = "I"

    usar_peajes_automaticos: bool = True

    valor_peajes: float = Field(
        default=0,
        ge=0,
        description="Valor manual de peajes por trayecto",
    )

    gastos_adicionales: float = Field(
        default=0,
        ge=0,
    )

    porcentaje_utilidad: float = Field(
        default=0,
        ge=0,
        le=100,
    )

    @field_validator("placa_vehiculo")
    @classmethod
    def normalizar_placa(cls, valor: str) -> str:
        placa = re.sub(r"[^A-Z0-9]", "", valor.upper().strip())

        if not re.fullmatch(r"[A-Z0-9]{5,8}", placa):
            raise ValueError(
                "La placa debe contener entre 5 y 8 letras o números."
            )

        return placa
