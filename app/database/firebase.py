from pathlib import Path

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore


BASE_DIR = Path(__file__).resolve().parents[2]
CLAVE_LOCAL = BASE_DIR / "firebase-key.json"


if not firebase_admin._apps:
    if CLAVE_LOCAL.exists():
        credencial = credentials.Certificate(
            str(CLAVE_LOCAL)
        )

        firebase_admin.initialize_app(
            credencial
        )
    else:
        firebase_admin.initialize_app()


db = firestore.client()