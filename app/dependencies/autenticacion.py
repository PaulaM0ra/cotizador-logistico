from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from firebase_admin import auth


def _extraer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Debes iniciar sesión.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    esquema, separador, token = authorization.partition(" ")

    if separador != " " or esquema.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El encabezado Authorization debe usar Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token.strip()


async def usuario_autenticado(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    token = _extraer_token(authorization)

    try:
        contenido = auth.verify_id_token(
            token,
            check_revoked=True,
        )
    except auth.ExpiredIdTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión expiró. Inicia sesión nuevamente.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except auth.RevokedIdTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión fue revocada.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except auth.InvalidIdTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token de autenticación no es válido.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No fue posible validar la sesión.",
        ) from error

    uid = contenido.get("uid") or contenido.get("sub")

    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El token no contiene un usuario válido.",
        )

    return {
        "uid": uid,
        "email": contenido.get("email"),
        "email_verificado": contenido.get("email_verified", False),
        "token": contenido,
    }


UsuarioActual = Annotated[dict, Depends(usuario_autenticado)]
