"""
config.py
=========
Punto ÚNICO de carga de configuración y secretos.

El resto del código NUNCA lee variables de entorno directamente:
siempre las importa desde aquí. Así la "configuración de seguridad"
queda separada y centralizada.
"""

import os
import sys

from dotenv import load_dotenv

# Carga el archivo .env (si existe) y vuelca sus claves en os.environ.
load_dotenv()


def _requerida(nombre: str) -> str:
    """
    Devuelve el valor de una variable de entorno obligatoria.
    Si no existe, detiene el programa con un mensaje claro en lugar
    de fallar más tarde con un error confuso.
    """
    valor = os.getenv(nombre)
    if not valor:
        print(
            f"[CONFIG] ERROR: falta la variable de entorno '{nombre}'.\n"
            f"         Revisa tu archivo .env (usa .env.example como guía).",
            file=sys.stderr,
        )
        sys.exit(1)
    return valor


# --- Variables OBLIGATORIAS ---
DISCORD_TOKEN: str = _requerida("DISCORD_TOKEN")
GEMINI_API_KEY: str = _requerida("GEMINI_API_KEY")
SUPABASE_URL: str = _requerida("SUPABASE_URL")
# SUPABASE_KEY = la Secret key nueva (sb_secret_...) o la antigua service_role.
SUPABASE_KEY: str = _requerida("SUPABASE_KEY")

# --- Variables OPCIONALES (con valor por defecto) ---
TARGET_CHANNEL_NAME: str = os.getenv("TARGET_CHANNEL_NAME", "subir-stats")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
