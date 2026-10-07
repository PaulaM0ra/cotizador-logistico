from fastapi import APIRouter, Query, status

from app.dependencies.autenticacion import UsuarioActual
from app.models.vehiculo import (
    ActualizarVehiculo,
    CrearVehiculo,
    VehiculoRespuesta,
)
from app.services.vehiculos import (
    actualizar_vehiculo,
    crear_vehiculo,
    desactivar_vehiculo,
    listar_vehiculos,
    obtener_vehiculo,
)


router = APIRouter(prefix="/vehiculos", tags=["Vehículos"])


@router.post("", response_model=VehiculoRespuesta, status_code=status.HTTP_201_CREATED)
async def registrar_vehiculo(datos: CrearVehiculo, usuario: UsuarioActual):
    return await crear_vehiculo(usuario, datos)


@router.get("", response_model=list[VehiculoRespuesta])
async def consultar_vehiculos(
    usuario: UsuarioActual,
    incluir_inactivos: bool = Query(default=False),
):
    return await listar_vehiculos(usuario, incluir_inactivos)


@router.get("/{placa}", response_model=VehiculoRespuesta)
async def consultar_vehiculo(placa: str, usuario: UsuarioActual):
    return await obtener_vehiculo(usuario, placa)


@router.patch("/{placa}", response_model=VehiculoRespuesta)
async def modificar_vehiculo(
    placa: str,
    cambios: ActualizarVehiculo,
    usuario: UsuarioActual,
):
    return await actualizar_vehiculo(usuario, placa, cambios)


@router.delete("/{placa}", response_model=VehiculoRespuesta)
async def eliminar_vehiculo(placa: str, usuario: UsuarioActual):
    return await desactivar_vehiculo(usuario, placa)
