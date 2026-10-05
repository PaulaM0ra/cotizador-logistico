from typing import Literal

from pydantic import BaseModel, Field


class Coordenada(BaseModel):
    longitud: float = Field(
        ...,
        ge=-180,
        le=180,
        description="Longitud geográfica"
    )

    latitud: float = Field(
        ...,
        ge=-90,
        le=90,
        description="Latitud geográfica"
    )


class SolicitudRuta(BaseModel):
    origen: Coordenada
    destino: Coordenada

    tipo_vehiculo: Literal["carro", "camion"] = Field(
        default="carro",
        description="Tipo de vehículo utilizado para calcular la ruta"
    )