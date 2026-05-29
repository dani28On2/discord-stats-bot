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
    game: str, discord_id: str, username: str, stat: str, value: int,
    is_vip: bool = False,
) -> dict:
    """
    Guarda la mejor marca del jugador en UNA stat de UN juego.

    Nota técnica: el valor se envía como STRING para que NUMERIC en
    Postgres lo reciba con precisión arbitraria. Si lo mandásemos como
    int de Python en JSON, los valores enormes (Sx en adelante) se
    convertirían a float y perderían dígitos.
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
        "best_value": str(value),  # NUMERIC acepta string directo
        "username": username,
        "is_vip": is_vip,
        "updated_at": ahora,
    }

    if actual is None:
        _supabase.table(LEADERBOARD).insert(fila).execute()
        return {"estado": "creado", "valor": value}

    # Convertimos lo que devuelve Supabase a int de Python (precisión arbitraria).
    record_previo = int(str(actual.get("best_value", 0)).split(".")[0])
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

    # Aunque no supere el récord, actualizamos is_vip por si cambió de estado.
    (
        _supabase.table(LEADERBOARD)
        .update({"is_vip": is_vip, "username": username})
        .eq("game", game)
        .eq("discord_id", discord_id)
        .eq("stat", stat)
        .execute()
    )
    return {"estado": "sin_cambios", "valor": record_previo}


async def guardar_stat(
    game: str, discord_id: str, username: str, stat: str, value: int,
    is_vip: bool = False,
) -> dict:
    return await asyncio.to_thread(
        _guardar_stat_sync, game, discord_id, username, stat, value, is_vip
    )


def _top_sync(game: str, stat: str, limit: int) -> list[dict]:
    """Top N de una stat concreta de un juego, ordenado descendentemente."""
    consulta = (
        _supabase.table(LEADERBOARD)
        .select("username,best_value,is_vip,updated_at")
        .eq("game", game)
        .eq("stat", stat)
        .order("best_value", desc=True)
        .limit(limit)
        .execute()
    )
    filas = consulta.data or []
    # Normalizamos best_value a int de Python (precisión arbitraria),
    # porque Supabase devuelve NUMERIC como string o float.
    for fila in filas:
        fila["best_value"] = int(str(fila.get("best_value", 0)).split(".")[0])
    return filas


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
# Ahora SOLO hay un canal de envío, así que el "último mensaje
# procesado" es un único valor global (no por juego).
async def obtener_ultimo_mensaje_global() -> str | None:
    return await state_get("last_message:submit")


async def guardar_ultimo_mensaje_global(message_id: str) -> None:
    return await state_set("last_message:submit", message_id)


# Mensaje (embed) del juego en el canal de leaderboards. No está fijado,
# simplemente se edita. Hay UNO por juego.
async def obtener_id_embed(game: str) -> str | None:
    return await state_get(f"embed:{game}")


async def guardar_id_embed(game: str, message_id: str) -> None:
    return await state_set(f"embed:{game}", message_id)


async def obtener_id_resumen(game: str) -> str | None:
    """ID del mensaje (con .json adjunto) en el canal de moderadores."""
    return await state_get(f"summary:{game}")


async def guardar_id_resumen(game: str, message_id: str) -> None:
    return await state_set(f"summary:{game}", message_id)
