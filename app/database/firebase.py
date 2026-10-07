import json
import logging
import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
CLAVE_LOCAL = BASE_DIR / "firebase-key.json"


def inicializar_firebase():
    if firebase_admin._apps:
        return firebase_admin.get_app()

    credencial_json = os.getenv(
        "FIREBASE_SERVICE_ACCOUNT_JSON"
    )

    if credencial_json:
        try:
            informacion = json.loads(
                credencial_json
            )

            credencial = credentials.Certificate(
                informacion
            )

            logger.info(
                "Firebase inicializado desde variable "
                "de entorno."
            )

            return firebase_admin.initialize_app(
                credencial
            )

        except json.JSONDecodeError as error:
            logger.exception(
                "FIREBASE_SERVICE_ACCOUNT_JSON "
                "no contiene JSON válido."
            )

            raise RuntimeError(
                "La variable "
                "FIREBASE_SERVICE_ACCOUNT_JSON "
                "no contiene JSON válido."
            ) from error

        except Exception as error:
            logger.exception(
                "No fue posible inicializar Firebase "
                "desde la variable de entorno."
            )

            raise RuntimeError(
                "No fue posible inicializar Firebase "
                "Admin."
            ) from error

    if CLAVE_LOCAL.exists():
        credencial = credentials.Certificate(
            str(CLAVE_LOCAL)
        )

        logger.info(
            "Firebase inicializado desde "
            "firebase-key.json local."
        )

        return firebase_admin.initialize_app(
            credencial
        )

    raise RuntimeError(
        "No se encontraron credenciales de Firebase. "
        "Configura FIREBASE_SERVICE_ACCOUNT_JSON."
    )


firebase_app = inicializar_firebase()
db = firestore.client(app=firebase_app)