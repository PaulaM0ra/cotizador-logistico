import json
import os
from pathlib import Path

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore


BASE_DIR = Path(__file__).resolve().parents[2]
CLAVE_LOCAL = BASE_DIR / "firebase-key.json"


def obtener_credencial():
    credencial_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

    if credencial_json:
        informacion = json.loads(credencial_json)
        return credentials.Certificate(informacion)

    if CLAVE_LOCAL.exists():
        return credentials.Certificate(str(CLAVE_LOCAL))

    return None


if not firebase_admin._apps:
    credencial = obtener_credencial()

    if credencial:
        firebase_admin.initialize_app(credencial)
    else:
        firebase_admin.initialize_app()


db = firestore.client()
