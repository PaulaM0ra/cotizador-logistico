from fastapi import APIRouter

from app.database.firebase import db
from app.models.vehiculo import Vehiculo

router = APIRouter(
    prefix="/vehiculos",
    tags=["Vehiculos"]
)


@router.post("/")
async def crear_vehiculo(vehiculo: Vehiculo):

    data = vehiculo.dict()

    db.collection("vehiculos").add(data)

    return {
        "mensaje": "Vehículo registrado correctamente"
    }
@router.get("/")
async def listar_vehiculos():

    documentos = db.collection("vehiculos").stream()

    vehiculos = []

    for doc in documentos:

        dato = doc.to_dict()
        dato["id"] = doc.id

        vehiculos.append(dato)

    return vehiculos
@router.get("/{vehiculo_id}")
async def obtener_vehiculo(vehiculo_id: str):

    doc = db.collection("vehiculos").document(vehiculo_id).get()

    if not doc.exists:
        raise HTTPException(
            status_code=404,
            detail="Vehículo no encontrado"
        )

    data = doc.to_dict()
    data["id"] = doc.id

    return data
@router.delete("/{vehiculo_id}")
async def eliminar_vehiculo(vehiculo_id: str):

    db.collection("vehiculos").document(
        vehiculo_id
    ).delete()

    return {
        "mensaje": "Vehículo eliminado"
    }
@router.put("/{vehiculo_id}")
async def actualizar_vehiculo(
    vehiculo_id: str,
    vehiculo: Vehiculo
):

    db.collection("vehiculos") \
      .document(vehiculo_id) \
      .update(vehiculo.dict())

    return {
        "mensaje": "Vehículo actualizado"
    }