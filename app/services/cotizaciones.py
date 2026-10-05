from fastapi import HTTPException

from app.models.cotizacion import SolicitudCotizacion
from app.models.ruta import SolicitudRuta
from app.services.peajes import detectar_peajes_en_ruta
from app.services.rutas import calcular_ruta


async def calcular_cotizacion(
    datos: SolicitudCotizacion
) -> dict:
    """
    Calcula la cotización completa del viaje.

    Incluye:
    - Ruta real.
    - Distancia total.
    - Consumo de combustible.
    - Peajes automáticos o manuales.
    - Gastos adicionales.
    - Porcentaje de utilidad.
    - Valor final del viaje.
    """

    solicitud_ruta = SolicitudRuta(
        origen=datos.origen,
        destino=datos.destino,
        tipo_vehiculo=datos.tipo_vehiculo
    )

    ruta = await calcular_ruta(
        solicitud_ruta
    )

    if not ruta.get("geometria"):
        raise HTTPException(
            status_code=502,
            detail=(
                "No se recibió la geometría necesaria "
                "para detectar los peajes."
            )
        )

    distancia_un_trayecto = ruta[
        "distancia_km"
    ]

    distancia_total = (
        distancia_un_trayecto
        * datos.numero_trayectos
    )

    galones = (
        distancia_total
        / datos.rendimiento_km_galon
    )

    costo_combustible = (
        galones
        * datos.precio_combustible_galon
    )

    categoria_peaje = getattr(
        datos,
        "categoria_peaje",
        "I"
    )

    usar_peajes_automaticos = getattr(
        datos,
        "usar_peajes_automaticos",
        True
    )

    resultado_peajes = {
        "categoria": categoria_peaje,
        "tolerancia_km": 0.8,
        "cantidad_peajes": 0,
        "peajes": [],
        "total_peajes_un_trayecto": 0,
        "advertencia": ""
    }

    if usar_peajes_automaticos:
        resultado_peajes = (
            await detectar_peajes_en_ruta(
                geometria=ruta["geometria"],
                categoria=categoria_peaje,
                tolerancia_km=0.8
            )
        )

        valor_peajes_un_trayecto = (
            resultado_peajes[
                "total_peajes_un_trayecto"
            ]
        )

        origen_valor_peajes = "automatico"

    else:
        valor_peajes_un_trayecto = (
            datos.valor_peajes
        )

        origen_valor_peajes = "manual"

    costo_total_peajes = (
        valor_peajes_un_trayecto
        * datos.numero_trayectos
    )

    subtotal = (
        costo_combustible
        + costo_total_peajes
        + datos.gastos_adicionales
    )

    utilidad = (
        subtotal
        * datos.porcentaje_utilidad
        / 100
    )

    total = (
        subtotal
        + utilidad
    )

    return {
        "ruta": {
            "perfil": ruta["perfil"],
            "distancia_un_trayecto_km": round(
                distancia_un_trayecto,
                2
            ),
            "distancia_total_km": round(
                distancia_total,
                2
            ),
            "duracion_un_trayecto_minutos": ruta[
                "duracion_minutos"
            ],
            "duracion_un_trayecto_horas": ruta[
                "duracion_horas"
            ],
            "numero_trayectos": (
                datos.numero_trayectos
            ),
            "geometria": ruta["geometria"]
        },

        "combustible": {
            "tipo": datos.tipo_combustible,
            "rendimiento_km_galon": (
                datos.rendimiento_km_galon
            ),
            "precio_por_galon": (
                datos.precio_combustible_galon
            ),
            "galones_estimados": round(
                galones,
                2
            ),
            "costo_estimado": round(
                costo_combustible,
                2
            )
        },

        "peajes": {
            "modo_calculo": origen_valor_peajes,
            "categoria": categoria_peaje,
            "cantidad_peajes": resultado_peajes[
                "cantidad_peajes"
            ],
            "detalle": resultado_peajes[
                "peajes"
            ],
            "valor_un_trayecto": round(
                valor_peajes_un_trayecto,
                2
            ),
            "numero_trayectos": (
                datos.numero_trayectos
            ),
            "costo_total": round(
                costo_total_peajes,
                2
            ),
            "advertencia": resultado_peajes.get(
                "advertencia",
                ""
            )
        },

        "costos": {
            "costo_combustible": round(
                costo_combustible,
                2
            ),
            "costo_peajes": round(
                costo_total_peajes,
                2
            ),
            "gastos_adicionales": round(
                datos.gastos_adicionales,
                2
            ),
            "subtotal_operativo": round(
                subtotal,
                2
            ),
            "porcentaje_utilidad": (
                datos.porcentaje_utilidad
            ),
            "valor_utilidad": round(
                utilidad,
                2
            ),
            "valor_cotizado": round(
                total,
                2
            )
        }
    }