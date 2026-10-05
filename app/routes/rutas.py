from fastapi import APIRouter

from app.models.ruta import SolicitudRuta
from app.services.rutas import calcular_ruta


router = APIRouter(
    prefix="/rutas",
    tags=["Rutas"]
)


@router.post("/calcular")
async def obtener_ruta(datos: SolicitudRuta):
    return await calcular_ruta(datos)