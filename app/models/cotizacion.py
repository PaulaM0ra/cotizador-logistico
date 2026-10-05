from typing import Literal

from pydantic import BaseModel, Field

from app.models.ruta import Coordenada


class SolicitudCotizacion(BaseModel):
    origen: Coordenada
    destino: Coordenada

    tipo_vehiculo: Literal[
        "carro",
        "camion"
    ] = "camion"

    tipo_combustible: Literal[
        "gasolina",
        "acpm"
    ] = "acpm"

    rendimiento_km_galon: float = Field(
        ...,
        gt=0,
        le=100,
        description=(
            "Rendimiento del vehículo "
            "en kilómetros por galón"
        )
    )

    precio_combustible_galon: float = Field(
        ...,
        gt=0,
        description=(
            "Precio del combustible "
            "por galón"
        )
    )

    numero_trayectos: int = Field(
        default=1,
        ge=1,
        le=2,
        description=(
            "1 para solo ida y "
            "2 para ida y regreso"
        )
    )

    categoria_peaje: Literal[
        "I",
        "II",
        "III",
        "IV",
        "V"
    ] = "I"

    usar_peajes_automaticos: bool = True

    valor_peajes: float = Field(
        default=0,
        ge=0,
        description=(
            "Valor manual de peajes "
            "por trayecto"
        )
    )

    gastos_adicionales: float = Field(
        default=0,
        ge=0
    )

    porcentaje_utilidad: float = Field(
        default=0,
        ge=0,
        le=100
    )