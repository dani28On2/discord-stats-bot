"""
database.py
===========
Capa de acceso a Supabase.

Dos responsabilidades:
  1. Guardar la MEJOR puntuación de cada jugador (tabla 'leaderboard').
  2. Recordar el ID del ÚLTIMO mensaje de Discord ya procesado
     (tabla 'bot_state'), para que el modo por lotes no repita
     mensajes entre una ejecución y la siguiente.
"""

import asyncio
from datetime import datetime, timezone

from supabase import Client, create_client

from src.config import SUPABASE_KEY, SUPABASE_URL

TABLE = "leaderboard"
STATE_TABLE = "bot_state"
STATE_KEY = "last_message_id"  # clave fija de la fila de estado

# create_client funciona igual con la nueva Secret key (sb_secret_...).
_supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------------------------------------------------------------
#  PUNTUACIONES
# ---------------------------------------------------------------------
def _guardar_sync(discord_id: str, username: str, score: int, kills: int) -> dict:
    """
    1. Busca el registro actual del jugador.
    2. Si no existe -> lo crea.
    3. Si existe y la nueva puntuación es mayor -> lo actualiza.
    4. Si no supera su récord -> no toca nada.
    """
    consulta = (
        _supabase.table(TABLE)
        .select("*")
        .eq("discord_id", discord_id)
        .execute()
    )
    registro_actual = consulta.data[0] if consulta.data else None

    ahora = datetime.now(timezone.utc).isoformat()
    fila = {
        "discord_id": discord_id,
        "username": username,
        "best_score": score,
        "best_kills": kills,
        "updated_at": ahora,
    }

    if registro_actual is None:
        _supabase.table(TABLE).insert(fila).execute()
        return {"estado": "creado", "puntuacion": score}

    record_previo = registro_actual.get("best_score", 0)
    if score > record_previo:
        _supabase.table(TABLE).update(fila).eq("discord_id", discord_id).execute()
        return {
            "estado": "actualizado",
            "puntuacion": score,
            "record_previo": record_previo,
        }

    return {"estado": "sin_cambios", "puntuacion": record_previo}


async def guardar_puntuacion(
    discord_id: str, username: str, score: int, kills: int
) -> dict:
    """Envoltura asíncrona (Supabase es bloqueante -> hilo aparte)."""
    return await asyncio.to_thread(
        _guardar_sync, discord_id, username, score, kills
    )


# ---------------------------------------------------------------------
#  ESTADO: último mensaje procesado
# ---------------------------------------------------------------------
def _obtener_ultimo_sync() -> str | None:
    """Devuelve el ID del último mensaje procesado, o None si es la 1ª vez."""
    consulta = (
        _supabase.table(STATE_TABLE)
        .select("value")
        .eq("key", STATE_KEY)
        .execute()
    )
    if consulta.data:
        return consulta.data[0]["value"]
    return None


def _guardar_ultimo_sync(message_id: str) -> None:
    """Guarda (crea o actualiza) el ID del último mensaje procesado."""
    _supabase.table(STATE_TABLE).upsert(
        {"key": STATE_KEY, "value": str(message_id)}
    ).execute()


async def obtener_ultimo_mensaje() -> str | None:
    return await asyncio.to_thread(_obtener_ultimo_sync)


async def guardar_ultimo_mensaje(message_id: str) -> None:
    return await asyncio.to_thread(_guardar_ultimo_sync, message_id)
