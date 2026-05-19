"""
config.py
=========
Punto ÚNICO de carga de configuración y secretos.
El resto del código nunca lee variables de entorno directamente:
siempre las importa desde aquí.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _requerida(nombre: str) -> str:
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
SUPABASE_KEY: str = _requerida("SUPABASE_KEY")

# --- Variables OPCIONALES ---
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# NOTA: ya no usamos TARGET_CHANNEL_NAME: los canales se obtienen
# automáticamente de games.py (uno por juego).
