from fastapi import APIRouter

from app.dependencies.autenticacion import UsuarioActual
from app.models.usuario import (
    ActualizarPerfilUsuario,
    CrearPerfilUsuario,
    UsuarioRespuesta,
)
from app.services.usuarios import (
    actualizar_perfil,
    crear_o_completar_perfil,
    obtener_perfil,
)


router = APIRouter(
    prefix="/usuarios",
    tags=["Usuarios"],
)


@router.post("/perfil", response_model=UsuarioRespuesta)
async def crear_perfil(
    datos: CrearPerfilUsuario,
    usuario: UsuarioActual,
):
    return await crear_o_completar_perfil(usuario, datos)


@router.get("/me", response_model=UsuarioRespuesta)
async def consultar_mi_perfil(usuario: UsuarioActual):
    return await obtener_perfil(usuario)


@router.patch("/me", response_model=UsuarioRespuesta)
async def modificar_mi_perfil(
    cambios: ActualizarPerfilUsuario,
    usuario: UsuarioActual,
):
    return await actualizar_perfil(usuario, cambios)
