import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


TipoVehiculo = Literal[
    "automovil",
    "camioneta",
    "campero",
    "motocarro",
    "furgon_ultraliviano",
    "turbo_liviana",
    "turbo_pesada",
    "bus",
    "buseta",
    "microbus",
    "camion_sencillo",
    "doble_troque",
    "cuatro_manos",
    "mini_mula",
    "tractocamion",
    "tractomula",
]
TipoCarroceria = Literal[
    "sin_furgon",
    "furgon_seco",
    "furgon_refrigerado",
    "furgon_congelado",
    "furgon_seco_capacete",
    "furgon_paqueteria",
    "furgon_blindado",
]
TipoCombustible = Literal["gasolina", "acpm"]
CategoriaPeaje = Literal["I", "II", "III", "IV", "V", "VI", "VII"]


class DimensionesVehiculo(BaseModel):
    largo_metros: float = Field(..., gt=0, le=30)
    ancho_metros: float = Field(..., gt=0, le=5)
    alto_metros: float = Field(..., gt=0, le=6)


class VehiculoBase(BaseModel):
    placa: str = Field(..., min_length=5, max_length=8)
    tipo_vehiculo: TipoVehiculo
    tipo_carroceria: TipoCarroceria = "sin_furgon"
    numero_ejes: int = Field(..., ge=2, le=9)
    categoria_peaje: CategoriaPeaje
    tipo_combustible: TipoCombustible
    rendimiento_km_galon: float = Field(..., gt=0, le=100)
    capacidad_carga_kg: float = Field(default=0, ge=0, le=100000)
    dimensiones: DimensionesVehiculo
    observaciones: str | None = Field(default=None, max_length=500)

    @field_validator("placa")
    @classmethod
    def normalizar_placa(cls, valor: str) -> str:
        placa = re.sub(r"[^A-Z0-9]", "", valor.upper().strip())
        if not re.fullmatch(r"[A-Z0-9]{5,8}", placa):
            raise ValueError("La placa debe contener entre 5 y 8 letras o números.")
        return placa

    @field_validator("observaciones")
    @classmethod
    def limpiar_observaciones(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        limpio = " ".join(valor.strip().split())
        return limpio or None

    @model_validator(mode="after")
    def validar_tipo_y_ejes(self):
        vehiculos_dos_ejes = {
            "automovil",
            "camioneta",
            "campero",
            "motocarro",
            "furgon_ultraliviano",
            "turbo_liviana",
            "turbo_pesada",
            "camion_sencillo",
        }

        vehiculos_tres_ejes = {
            "doble_troque",
        }

        vehiculos_cuatro_ejes = {
            "cuatro_manos",
        }

        articulados = {
            "mini_mula",
            "tractocamion",
            "tractomula",
        }

        if (
            self.tipo_vehiculo
            in vehiculos_dos_ejes
            and self.numero_ejes != 2
        ):
            raise ValueError(
                "El tipo seleccionado debe registrarse "
                "con 2 ejes."
            )

        if (
            self.tipo_vehiculo
            in vehiculos_tres_ejes
            and self.numero_ejes != 3
        ):
            raise ValueError(
                "El doble troque debe registrarse "
                "con 3 ejes."
            )

        if (
            self.tipo_vehiculo
            in vehiculos_cuatro_ejes
            and self.numero_ejes != 4
        ):
            raise ValueError(
                "El cuatro manos debe registrarse "
                "con 4 ejes."
            )

        if (
            self.tipo_vehiculo in articulados
            and self.numero_ejes < 3
        ):
            raise ValueError(
                "Los vehículos articulados deben "
                "tener al menos 3 ejes."
            )

        return self

class CrearVehiculo(VehiculoBase):
    pass


class ActualizarVehiculo(BaseModel):
    tipo_vehiculo: TipoVehiculo | None = None
    numero_ejes: int | None = Field(default=None, ge=2, le=9)
    tipo_carroceria: TipoCarroceria | None = None
    categoria_peaje: CategoriaPeaje | None = None
    tipo_combustible: TipoCombustible | None = None
    rendimiento_km_galon: float | None = Field(default=None, gt=0, le=100)
    capacidad_carga_kg: float | None = Field(default=None, ge=0, le=100000)
    dimensiones: DimensionesVehiculo | None = None
    observaciones: str | None = Field(default=None, max_length=500)
    activo: bool | None = None


class VehiculoRespuesta(VehiculoBase):
    uid_propietario: str
    activo: bool
    creado_en: datetime
    actualizado_en: datetime
