from fastapi import APIRouter

from app.models.cotizacion import SolicitudCotizacion
from app.services.cotizaciones import calcular_cotizacion

router = APIRouter(prefix="/cotizaciones", tags=["Cotizaciones"])


@router.post("/calcular")
async def obtener_cotizacion(datos: SolicitudCotizacion):
    return await calcular_cotizacion(datos)
