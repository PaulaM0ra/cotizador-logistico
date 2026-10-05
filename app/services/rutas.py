import os
from pathlib import Path

import certifi
import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

from app.models.ruta import SolicitudRuta


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE)

ORS_API_KEY = os.getenv("ORS_API_KEY")
ORS_BASE_URL = "https://api.openrouteservice.org/v2/directions"


def seleccionar_perfil(tipo_vehiculo: str) -> str:
    perfiles = {
        "carro": "driving-car",
        "camion": "driving-hgv"
    }

    perfil = perfiles.get(tipo_vehiculo.lower())

    if not perfil:
        raise HTTPException(
            status_code=400,
            detail=(
                "El tipo de vehículo debe ser "
                "'carro' o 'camion'."
            )
        )

    return perfil


async def calcular_ruta(
    datos: SolicitudRuta
) -> dict:
    if not ORS_API_KEY:
        raise HTTPException(
            status_code=500,
            detail=(
                "No se configuró ORS_API_KEY "
                "en el archivo .env."
            )
        )

    perfil = seleccionar_perfil(
        datos.tipo_vehiculo
    )

    url = (
        f"{ORS_BASE_URL}/"
        f"{perfil}/geojson"
    )

    coordenadas = [
        [
            datos.origen.longitud,
            datos.origen.latitud
        ],
        [
            datos.destino.longitud,
            datos.destino.latitud
        ]
    ]

    encabezados = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json",
        "Accept": (
            "application/json, "
            "application/geo+json"
        )
    }

    cuerpo = {
        "coordinates": coordenadas,
        "instructions": True,
        "language": "es"
    }

    try:
        print(
            "Consultando openrouteservice:",
            url
        )

        print(
            "Perfil utilizado:",
            perfil
        )

        print(
            "API key configurada:",
            bool(ORS_API_KEY)
        )

        async with httpx.AsyncClient(
            timeout=30.0,
            verify=certifi.where(),
            trust_env=False
        ) as cliente:
            respuesta = await cliente.post(
                url,
                headers=encabezados,
                json=cuerpo
            )

    except httpx.TimeoutException as error:
        print(
            "Tiempo agotado al consultar ORS:",
            repr(error)
        )

        raise HTTPException(
            status_code=504,
            detail={
                "mensaje": (
                    "El servicio de rutas tardó "
                    "demasiado en responder."
                ),
                "tipo_error": type(error).__name__,
                "error": str(error)
            }
        ) from error

    except httpx.RequestError as error:
        print("=" * 60)
        print("ERROR EXACTO DE CONEXIÓN CON ORS")
        print("Tipo:", type(error).__name__)
        print("Detalle:", str(error))
        print("Representación:", repr(error))
        print("URL:", url)
        print("=" * 60)

        raise HTTPException(
            status_code=503,
            detail={
                "mensaje": (
                    "No fue posible conectarse "
                    "con openrouteservice."
                ),
                "tipo_error": type(error).__name__,
                "error": str(error)
            }
        ) from error

    print(
        "Estado de openrouteservice:",
        respuesta.status_code
    )

    if respuesta.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail=(
                "La clave de openrouteservice "
                "no es válida."
            )
        )

    if respuesta.status_code == 403:
        raise HTTPException(
            status_code=403,
            detail=(
                "La solicitud fue rechazada "
                "por openrouteservice."
            )
        )

    if respuesta.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail=(
                "Se alcanzó el límite de consultas "
                "de openrouteservice."
            )
        )

    if respuesta.status_code >= 400:
        try:
            detalle = respuesta.json()
        except ValueError:
            detalle = respuesta.text

        raise HTTPException(
            status_code=respuesta.status_code,
            detail={
                "mensaje": (
                    "No fue posible calcular "
                    "la ruta."
                ),
                "respuesta_servicio": detalle
            }
        )

    try:
        resultado = respuesta.json()
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "El servicio de rutas devolvió "
                "una respuesta no válida."
            )
        ) from error

    if not resultado.get("features"):
        raise HTTPException(
            status_code=404,
            detail=(
                "No se encontró una ruta entre "
                "las coordenadas indicadas."
            )
        )

    feature = resultado["features"][0]
    propiedades = feature.get(
        "properties",
        {}
    )

    resumen = propiedades.get(
        "summary"
    )

    if not resumen:
        raise HTTPException(
            status_code=502,
            detail=(
                "La respuesta del servicio no contiene "
                "el resumen de la ruta."
            )
        )

    distancia_metros = resumen.get(
        "distance",
        0
    )

    duracion_segundos = resumen.get(
        "duration",
        0
    )

    return {
        "perfil": perfil,
        "distancia_km": round(
            distancia_metros / 1000,
            2
        ),
        "duracion_minutos": round(
            duracion_segundos / 60,
            2
        ),
        "duracion_horas": round(
            duracion_segundos / 3600,
            2
        ),
        "geometria": feature.get(
            "geometry"
        ),
        "instrucciones": propiedades.get(
            "segments",
            []
        ),
        "origen": datos.origen.model_dump(),
        "destino": datos.destino.model_dump()
    }