"""
database.py
===========
Capa de acceso a Supabase.

Regla de negocio: solo guardamos la MEJOR puntuación de cada jugador.
Si la nueva puntuación no supera la que ya tenía registrada, se conserva
la antigua. El jugador se identifica por su ID de Discord (único).
"""

import asyncio
from datetime import datetime, timezone

from supabase import Client, create_client

from src.config import SUPABASE_KEY, SUPABASE_URL

# Tabla esperada en Supabase (ver schema.sql del repositorio):
#   discord_id  text  PRIMARY KEY
#   username    text
#   best_score  int
#   best_kills  int
#   updated_at  timestamptz
TABLE = "leaderboard"

# create_client funciona igual con la nueva Secret key (sb_secret_...)
# que con la antigua service_role: no hay que cambiar nada aquí.
_supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def _guardar_sync(discord_id: str, username: str, score: int, kills: int) -> dict:
    """
    Lógica síncrona:
      1. Busca el registro actual del jugador.
      2. Si no existe -> lo crea.
      3. Si existe y la nueva puntuación es mayor -> lo actualiza.
      4. Si no supera su récord -> no toca nada.

    Devuelve un dict describiendo qué pasó, para que el bot mande
    el mensaje de confirmación adecuado.
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

    # Caso 1: jugador nuevo
    if registro_actual is None:
        _supabase.table(TABLE).insert(fila).execute()
        return {"estado": "creado", "puntuacion": score}

    # Caso 2: ya existía -> ¿supera su récord?
    record_previo = registro_actual.get("best_score", 0)
    if score > record_previo:
        _supabase.table(TABLE).update(fila).eq("discord_id", discord_id).execute()
        return {
            "estado": "actualizado",
            "puntuacion": score,
            "record_previo": record_previo,
        }

    # Caso 3: no mejora su marca
    return {"estado": "sin_cambios", "puntuacion": record_previo}


async def guardar_puntuacion(
    discord_id: str, username: str, score: int, kills: int
) -> dict:
    """
    Envoltura asíncrona. El cliente de Supabase también es bloqueante,
    así que lo ejecutamos en un hilo aparte igual que hicimos con Gemini.
    """
    return await asyncio.to_thread(
        _guardar_sync, discord_id, username, score, kills
    )
