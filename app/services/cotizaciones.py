from fastapi import HTTPException

from app.database.firebase import db
from app.models.cotizacion import SolicitudCotizacion
from app.models.ruta import SolicitudRuta
from app.services.peajes import detectar_peajes_en_ruta
from app.services.rutas import calcular_ruta


COLECCION_VEHICULOS = "vehiculos"

TIPOS_LIVIANOS = {
    "automovil",
    "camioneta",
    "campero",
    "motocarro",
}


def _tipo_general(tipo_registrado: str) -> str:
    return "carro" if tipo_registrado in TIPOS_LIVIANOS else "camion"


async def _obtener_vehiculo_validado(
    placa: str,
    uid_usuario: str,
) -> dict:
    referencia = db.collection(COLECCION_VEHICULOS).document(placa)
    documento = referencia.get()

    if not documento.exists:
        raise HTTPException(
            status_code=404,
            detail="El vehículo seleccionado no está registrado.",
        )

    vehiculo = documento.to_dict()

    if vehiculo.get("uid_propietario") != uid_usuario:
        raise HTTPException(
            status_code=403,
            detail="No puedes cotizar con un vehículo de otro usuario.",
        )

    if not vehiculo.get("activo", True):
        raise HTTPException(
            status_code=409,
            detail="El vehículo seleccionado está desactivado.",
        )

    campos_requeridos = {
        "tipo_vehiculo",
        "numero_ejes",
        "categoria_peaje",
        "tipo_combustible",
        "rendimiento_km_galon",
    }
    faltantes = [
        campo
        for campo in campos_requeridos
        if vehiculo.get(campo) is None
    ]

    if faltantes:
        raise HTTPException(
            status_code=422,
            detail={
                "mensaje": (
                    "El vehículo no tiene toda la información necesaria "
                    "para calcular la cotización."
                ),
                "campos_faltantes": sorted(faltantes),
            },
        )

    rendimiento = float(vehiculo["rendimiento_km_galon"])
    if rendimiento <= 0:
        raise HTTPException(
            status_code=422,
            detail="El rendimiento registrado del vehículo no es válido.",
        )

    return vehiculo


async def calcular_cotizacion(
    datos: SolicitudCotizacion,
    usuario: dict,
) -> dict:
    """Calcula la cotización usando el vehículo validado en Firestore."""

    vehiculo = await _obtener_vehiculo_validado(
        placa=datos.placa_vehiculo,
        uid_usuario=usuario["uid"],
    )

    tipo_registrado = str(vehiculo["tipo_vehiculo"])
    tipo_vehiculo = _tipo_general(tipo_registrado)
    tipo_carroceria = vehiculo.get("tipo_carroceria", "sin_furgon")
    numero_ejes = int(vehiculo["numero_ejes"])
    categoria_peaje = str(vehiculo["categoria_peaje"])
    tipo_combustible = str(vehiculo["tipo_combustible"])
    rendimiento_km_galon = float(vehiculo["rendimiento_km_galon"])

    solicitud_ruta = SolicitudRuta(
        origen=datos.origen,
        destino=datos.destino,
        tipo_vehiculo=tipo_vehiculo,
    )
    ruta = await calcular_ruta(solicitud_ruta)

    if not ruta.get("geometria"):
        raise HTTPException(
            status_code=502,
            detail=(
                "No se recibió la geometría necesaria "
                "para detectar los peajes."
            ),
        )

    distancia_un_trayecto = float(ruta["distancia_km"])
    distancia_total = distancia_un_trayecto * datos.numero_trayectos
    galones = distancia_total / rendimiento_km_galon
    costo_combustible = galones * datos.precio_combustible_galon

    resultado_peajes = {
        "categoria": categoria_peaje,
        "tolerancia_km": 3.0,
        "cantidad_peajes": 0,
        "peajes": [],
        "total_peajes_un_trayecto": 0,
        "fuentes_consultadas": [],
        "fuentes_con_error": [],
        "peajes_mas_cercanos": [],
        "peajes_sin_tarifa": [],
        "advertencia": "",
    }

    if datos.usar_peajes_automaticos:
        resultado_peajes = await detectar_peajes_en_ruta(
            geometria=ruta["geometria"],
            categoria=categoria_peaje,
            tolerancia_km=3.0,
        )
        valor_peajes_un_trayecto = float(
            resultado_peajes.get("total_peajes_un_trayecto", 0)
        )
        origen_valor_peajes = "automatico"
    else:
        valor_peajes_un_trayecto = datos.valor_peajes
        origen_valor_peajes = "manual"

    costo_total_peajes = (
        valor_peajes_un_trayecto * datos.numero_trayectos
    )
    subtotal = (
        costo_combustible
        + costo_total_peajes
        + datos.gastos_adicionales
    )
    utilidad = subtotal * datos.porcentaje_utilidad / 100
    total = subtotal + utilidad

    return {
        "vehiculo": {
            "placa": datos.placa_vehiculo,
            "tipo_registrado": tipo_registrado,
            "tipo_general_ruta": tipo_vehiculo,
            "tipo_carroceria": tipo_carroceria,
            "numero_ejes": numero_ejes,
            "categoria_peaje": categoria_peaje,
            "tipo_combustible": tipo_combustible,
            "rendimiento_km_galon": rendimiento_km_galon,
            "capacidad_carga_kg": vehiculo.get("capacidad_carga_kg", 0),
            "dimensiones": vehiculo.get("dimensiones"),
        },
        "ruta": {
            "perfil": ruta["perfil"],
            "distancia_un_trayecto_km": round(
                distancia_un_trayecto,
                2,
            ),
            "distancia_total_km": round(distancia_total, 2),
            "duracion_un_trayecto_minutos": ruta["duracion_minutos"],
            "duracion_un_trayecto_horas": ruta["duracion_horas"],
            "numero_trayectos": datos.numero_trayectos,
            "geometria": ruta["geometria"],
        },
        "combustible": {
            "tipo": tipo_combustible,
            "rendimiento_km_galon": rendimiento_km_galon,
            "precio_por_galon": datos.precio_combustible_galon,
            "galones_estimados": round(galones, 2),
            "costo_estimado": round(costo_combustible, 2),
        },
        "peajes": {
            "modo_calculo": origen_valor_peajes,
            "categoria": categoria_peaje,
            "tolerancia_km": resultado_peajes.get(
                "tolerancia_km",
                3.0,
            ),
            "cantidad_peajes": resultado_peajes.get(
                "cantidad_peajes",
                0,
            ),
            "detalle": resultado_peajes.get(
                "peajes",
                [],
            ),
            "valor_un_trayecto": round(
                valor_peajes_un_trayecto,
                2,
            ),
            "numero_trayectos": datos.numero_trayectos,
            "costo_total": round(costo_total_peajes, 2),
            "fuentes_consultadas": resultado_peajes.get(
                "fuentes_consultadas",
                [],
            ),
            "fuentes_con_error": resultado_peajes.get(
                "fuentes_con_error",
                [],
            ),
            "peajes_mas_cercanos": resultado_peajes.get(
                "peajes_mas_cercanos",
                [],
            ),
            "peajes_sin_tarifa": resultado_peajes.get(
                "peajes_sin_tarifa",
                [],
            ),
            "advertencia": resultado_peajes.get(
                "advertencia",
                "",
            ),
        },
        "costos": {
            "costo_combustible": round(costo_combustible, 2),
            "costo_peajes": round(costo_total_peajes, 2),
            "gastos_adicionales": round(datos.gastos_adicionales, 2),
            "subtotal_operativo": round(subtotal, 2),
            "porcentaje_utilidad": datos.porcentaje_utilidad,
            "valor_utilidad": round(utilidad, 2),
            "valor_cotizado": round(total, 2),
        },
    }
