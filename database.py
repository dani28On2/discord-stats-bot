"""
database.py
===========
Acceso a Supabase.

Tablas:
  leaderboard(game, discord_id, stat, best_value, username, updated_at)
    PK: (game, discord_id, stat)
    -> Una fila por (juego, jugador, estadística). Permite que cada stat
       tenga su récord independiente.

  bot_state(key, value)
    -> Almacén clave/valor para datos sueltos. Lo usamos para:
         last_message:<game>   -> ID del último mensaje procesado en ese canal
         pinned:<game>:<stat>  -> ID del mensaje fijado del Top 10 de esa stat
"""

import asyncio
from datetime import datetime, timezone

from supabase import Client, create_client

from config import SUPABASE_KEY, SUPABASE_URL

LEADERBOARD = "leaderboard"
STATE = "bot_state"

_supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# =====================================================================
#  PUNTUACIONES
# =====================================================================
def _guardar_stat_sync(
    game: str, discord_id: str, username: str, stat: str, value: int
) -> dict:
    """
    Guarda la mejor marca del jugador en UNA stat de UN juego.

    Devuelve un dict con el resultado:
      {"estado": "creado"|"actualizado"|"sin_cambios", ...}
    """
    consulta = (
        _supabase.table(LEADERBOARD)
        .select("*")
        .eq("game", game)
        .eq("discord_id", discord_id)
        .eq("stat", stat)
        .execute()
    )
    actual = consulta.data[0] if consulta.data else None

    ahora = datetime.now(timezone.utc).isoformat()
    fila = {
        "game": game,
        "discord_id": discord_id,
        "stat": stat,
        "best_value": value,
        "username": username,
        "updated_at": ahora,
    }

    if actual is None:
        _supabase.table(LEADERBOARD).insert(fila).execute()
        return {"estado": "creado", "valor": value}

    record_previo = actual.get("best_value", 0)
    if value > record_previo:
        (
            _supabase.table(LEADERBOARD)
            .update(fila)
            .eq("game", game)
            .eq("discord_id", discord_id)
            .eq("stat", stat)
            .execute()
        )
        return {"estado": "actualizado", "valor": value, "record_previo": record_previo}

    return {"estado": "sin_cambios", "valor": record_previo}


async def guardar_stat(
    game: str, discord_id: str, username: str, stat: str, value: int
) -> dict:
    return await asyncio.to_thread(
        _guardar_stat_sync, game, discord_id, username, stat, value
    )


def _top_sync(game: str, stat: str, limit: int) -> list[dict]:
    """Top N de una stat concreta de un juego, ordenado descendentemente."""
    consulta = (
        _supabase.table(LEADERBOARD)
        .select("username,best_value,updated_at")
        .eq("game", game)
        .eq("stat", stat)
        .order("best_value", desc=True)
        .limit(limit)
        .execute()
    )
    return consulta.data or []


async def obtener_top(game: str, stat: str, limit: int = 10) -> list[dict]:
    return await asyncio.to_thread(_top_sync, game, stat, limit)


# =====================================================================
#  ESTADO (almacén clave/valor)
# =====================================================================
def _state_get_sync(key: str) -> str | None:
    consulta = (
        _supabase.table(STATE).select("value").eq("key", key).execute()
    )
    return consulta.data[0]["value"] if consulta.data else None


def _state_set_sync(key: str, value: str) -> None:
    _supabase.table(STATE).upsert({"key": key, "value": str(value)}).execute()


async def state_get(key: str) -> str | None:
    return await asyncio.to_thread(_state_get_sync, key)


async def state_set(key: str, value: str) -> None:
    return await asyncio.to_thread(_state_set_sync, key, value)


# Helpers semánticos para que batch_update.py se lea mejor.
async def obtener_ultimo_mensaje(game: str) -> str | None:
    return await state_get(f"last_message:{game}")


async def guardar_ultimo_mensaje(game: str, message_id: str) -> None:
    return await state_set(f"last_message:{game}", message_id)


async def obtener_id_pinned(game: str, stat: str) -> str | None:
    return await state_get(f"pinned:{game}:{stat}")


async def guardar_id_pinned(game: str, stat: str, message_id: str) -> None:
    return await state_set(f"pinned:{game}:{stat}", message_id)
