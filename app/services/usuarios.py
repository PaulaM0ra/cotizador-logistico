from datetime import datetime, timezone

from fastapi import HTTPException
from firebase_admin import firestore

from app.database.firebase import db
from app.models.usuario import (
    ActualizarPerfilUsuario,
    CrearPerfilUsuario,
)


COLECCION_USUARIOS = "usuarios"


def _fecha(valor) -> datetime:
    if isinstance(valor, datetime):
        return valor
    return datetime.now(timezone.utc)


def _serializar(documento: dict, uid: str) -> dict:
    return {
        "uid": uid,
        "email": documento.get("email"),
        "nombre": documento.get("nombre", ""),
        "telefono": documento.get("telefono"),
        "rol": documento.get("rol", "conductor"),
        "activo": documento.get("activo", True),
        "creado_en": _fecha(documento.get("creado_en")),
        "actualizado_en": _fecha(documento.get("actualizado_en")),
    }


async def crear_o_completar_perfil(
    usuario: dict,
    datos: CrearPerfilUsuario,
) -> dict:
    uid = usuario["uid"]
    referencia = db.collection(COLECCION_USUARIOS).document(uid)
    existente = referencia.get()

    if existente.exists:
        documento = existente.to_dict()

        if not documento.get("activo", True):
            raise HTTPException(
                status_code=403,
                detail="La cuenta está desactivada.",
            )

        return _serializar(documento, uid)

    ahora = datetime.now(timezone.utc)
    documento = {
        "email": usuario.get("email"),
        "nombre": datos.nombre,
        "telefono": datos.telefono,
        # Nunca se acepta administrador desde autorregistro.
        "rol": "conductor",
        "activo": True,
        "creado_en": ahora,
        "actualizado_en": ahora,
    }
    referencia.set(documento)
    return _serializar(documento, uid)


async def obtener_perfil(usuario: dict) -> dict:
    uid = usuario["uid"]
    documento = db.collection(COLECCION_USUARIOS).document(uid).get()

    if not documento.exists:
        raise HTTPException(
            status_code=404,
            detail="El perfil del usuario todavía no existe.",
        )

    datos = documento.to_dict()

    if not datos.get("activo", True):
        raise HTTPException(
            status_code=403,
            detail="La cuenta está desactivada.",
        )

    return _serializar(datos, uid)


async def actualizar_perfil(
    usuario: dict,
    cambios: ActualizarPerfilUsuario,
) -> dict:
    uid = usuario["uid"]
    referencia = db.collection(COLECCION_USUARIOS).document(uid)
    existente = referencia.get()

    if not existente.exists:
        raise HTTPException(
            status_code=404,
            detail="El perfil del usuario todavía no existe.",
        )

    actualizacion = cambios.model_dump(exclude_unset=True)
    actualizacion["actualizado_en"] = firestore.SERVER_TIMESTAMP
    referencia.update(actualizacion)

    resultado = referencia.get().to_dict()
    return _serializar(resultado, uid)
