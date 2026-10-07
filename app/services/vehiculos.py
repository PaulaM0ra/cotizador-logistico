from datetime import datetime, timezone

from fastapi import HTTPException
from firebase_admin import firestore

from app.database.firebase import db
from app.models.vehiculo import ActualizarVehiculo, CrearVehiculo


COLECCION_VEHICULOS = "vehiculos"


def _fecha(valor) -> datetime:
    return valor if isinstance(valor, datetime) else datetime.now(timezone.utc)


def _serializar(documento: dict, placa: str) -> dict:
    return {
        "placa": placa,
        "uid_propietario": documento["uid_propietario"],
        "tipo_vehiculo": documento["tipo_vehiculo"],
        "tipo_carroceria": documento.get(
    "tipo_carroceria",
    "sin_furgon"
),
        "numero_ejes": documento["numero_ejes"],
        "categoria_peaje": documento["categoria_peaje"],
        "tipo_combustible": documento["tipo_combustible"],
        "rendimiento_km_galon": documento["rendimiento_km_galon"],
        "capacidad_carga_kg": documento.get("capacidad_carga_kg", 0),
        "dimensiones": documento["dimensiones"],
        "observaciones": documento.get("observaciones"),
        "activo": documento.get("activo", True),
        "creado_en": _fecha(documento.get("creado_en")),
        "actualizado_en": _fecha(documento.get("actualizado_en")),
    }


def _validar_propietario(documento: dict, uid: str) -> None:
    if documento.get("uid_propietario") != uid:
        raise HTTPException(status_code=403, detail="No puedes acceder a este vehículo.")


async def crear_vehiculo(usuario: dict, datos: CrearVehiculo) -> dict:
    referencia = db.collection(COLECCION_VEHICULOS).document(datos.placa)
    existente = referencia.get()

    if existente.exists:
        raise HTTPException(status_code=409, detail="La placa ya está registrada.")

    ahora = datetime.now(timezone.utc)
    documento = datos.model_dump(exclude={"placa"})
    documento.update({
        "uid_propietario": usuario["uid"],
        "activo": True,
        "creado_en": ahora,
        "actualizado_en": ahora,
    })
    referencia.set(documento)
    return _serializar(documento, datos.placa)


async def listar_vehiculos(usuario: dict, incluir_inactivos: bool = False) -> list[dict]:
    consulta = db.collection(COLECCION_VEHICULOS).where(
        filter=firestore.FieldFilter("uid_propietario", "==", usuario["uid"])
    )
    resultados = []

    for documento in consulta.stream():
        datos = documento.to_dict()
        if incluir_inactivos or datos.get("activo", True):
            resultados.append(_serializar(datos, documento.id))

    resultados.sort(key=lambda item: item["placa"])
    return resultados


async def obtener_vehiculo(usuario: dict, placa: str) -> dict:
    placa_normalizada = placa.upper().replace("-", "").replace(" ", "")
    documento = db.collection(COLECCION_VEHICULOS).document(placa_normalizada).get()

    if not documento.exists:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado.")

    datos = documento.to_dict()
    _validar_propietario(datos, usuario["uid"])
    return _serializar(datos, documento.id)


async def actualizar_vehiculo(
    usuario: dict,
    placa: str,
    cambios: ActualizarVehiculo,
) -> dict:
    placa_normalizada = placa.upper().replace("-", "").replace(" ", "")
    referencia = db.collection(COLECCION_VEHICULOS).document(placa_normalizada)
    existente = referencia.get()

    if not existente.exists:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado.")

    actual = existente.to_dict()
    _validar_propietario(actual, usuario["uid"])

    actualizacion = cambios.model_dump(exclude_unset=True)
    actualizacion["actualizado_en"] = firestore.SERVER_TIMESTAMP
    referencia.update(actualizacion)

    nuevo = referencia.get().to_dict()
    return _serializar(nuevo, placa_normalizada)


async def desactivar_vehiculo(usuario: dict, placa: str) -> dict:
    return await actualizar_vehiculo(
        usuario,
        placa,
        ActualizarVehiculo(activo=False),
    )
