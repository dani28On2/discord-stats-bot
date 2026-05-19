"""
batch_update.py
================
Versión POR LOTES del bot (la que ejecuta GitHub Actions).

A diferencia de main.py, esto NO se queda escuchando. Hace lo siguiente
y se cierra:

  1. Se conecta a Discord.
  2. Mira en Supabase cuál fue el último mensaje procesado.
  3. Lee del canal SOLO los mensajes nuevos desde entonces.
  4. Cada captura nueva -> Gemini -> Supabase -> mensaje de confirmación.
  5. Guarda el ID del mensaje más reciente y cierra la conexión.

Ejecutar con:  python batch_update.py
"""

import asyncio

import discord

from src.config import DISCORD_TOKEN, TARGET_CHANNEL_NAME
from src.database import (
    guardar_puntuacion,
    guardar_ultimo_mensaje,
    obtener_ultimo_mensaje,
)
from src.gemini_service import extract_stats_from_image

# En la PRIMERA ejecución (sin estado previo) no procesamos todo el
# historial del canal para no inundarlo de confirmaciones: solo los
# últimos N mensajes. Súbelo si tienes un backlog mayor que recuperar.
BACKFILL_PRIMERA_VEZ = 25

# Tope de mensajes por ejecución (evita tandas gigantes inesperadas).
MAX_POR_EJECUCION = 200

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


def _es_imagen(attachment: discord.Attachment) -> bool:
    return (attachment.content_type or "").startswith("image/")


async def _procesar_mensaje(message: discord.Message) -> None:
    """Procesa UN mensaje con imagen (misma lógica que el main.py original)."""
    attachment = message.attachments[0]
    if not _es_imagen(attachment):
        return

    try:
        image_bytes = await attachment.read()
        stats = await extract_stats_from_image(image_bytes, attachment.content_type)
    except Exception as error:
        print(f"[WARN] Mensaje {message.id}: fallo al analizar con Gemini: {error}")
        return

    if not stats.stats_detected or stats.score <= 0:
        await message.reply(
            "🔍 No conseguí leer las estadísticas de esta captura "
            "(¿borrosa o sin datos visibles?).",
            mention_author=False,
        )
        return

    try:
        resultado = await guardar_puntuacion(
            discord_id=str(message.author.id),
            username=str(message.author),
            score=stats.score,
            kills=stats.kills,
        )
    except Exception as error:
        print(f"[ERROR] Mensaje {message.id}: fallo al guardar en Supabase: {error}")
        return

    jugador = stats.player_name or message.author.display_name
    estado = resultado["estado"]

    if estado == "creado":
        texto = (
            f"✅ ¡Bienvenido al ranking, **{jugador}**! "
            f"Puntuación de **{stats.score:,}** registrada "
            f"({stats.kills} bajas)."
        )
    elif estado == "actualizado":
        texto = (
            f"🏆 ¡Nuevo récord, **{jugador}**! **{stats.score:,}** puntos "
            f"(antes: {resultado['record_previo']:,})."
        )
    else:  # sin_cambios
        texto = (
            f"📊 Registrado, pero tu mejor marca sigue siendo "
            f"**{resultado['puntuacion']:,}**."
        )

    await message.reply(texto, mention_author=False)


@client.event
async def on_ready():
    """Todo el trabajo ocurre aquí; al final cerramos el cliente sí o sí."""
    print(f"[BATCH] Conectado como {client.user}")
    try:
        # 1) Localizar el canal objetivo por nombre.
        canal = None
        for ch in client.get_all_channels():
            if isinstance(ch, discord.TextChannel) and ch.name == TARGET_CHANNEL_NAME:
                canal = ch
                break

        if canal is None:
            print(
                f"[ERROR] No encuentro el canal de texto "
                f"'#{TARGET_CHANNEL_NAME}'. ¿El bot está en el servidor y "
                f"tiene permiso para verlo?"
            )
            return

        # 2) ¿Por dónde íbamos?
        ultimo_id = await obtener_ultimo_mensaje()

        # 3) Leer mensajes según sea primera vez o no.
        if ultimo_id is None:
            print("[BATCH] Primera ejecución: reviso los últimos mensajes.")
            recientes = [
                m
                async for m in canal.history(
                    limit=BACKFILL_PRIMERA_VEZ, oldest_first=False
                )
            ]
            mensajes = list(reversed(recientes))  # de más antiguo a más nuevo
        else:
            despues_de = discord.Object(id=int(ultimo_id))
            mensajes = [
                m
                async for m in canal.history(
                    limit=MAX_POR_EJECUCION, after=despues_de, oldest_first=True
                )
            ]

        if not mensajes:
            print("[BATCH] No hay mensajes nuevos. Nada que hacer.")
            return

        # 4) Procesar solo los que tengan imagen y no sean del propio bot.
        procesados = 0
        for message in mensajes:
            if message.author == client.user:
                continue
            if not message.attachments:
                continue
            await _procesar_mensaje(message)
            procesados += 1

        # 5) Guardar el ID del mensaje MÁS RECIENTE de la tanda.
        #    Nota: avanzamos el puntero aunque alguno fallase, para no
        #    quedarnos reintentando eternamente una captura mala.
        id_mas_reciente = max(m.id for m in mensajes)
        await guardar_ultimo_mensaje(str(id_mas_reciente))

        print(
            f"[BATCH] Listo. Mensajes con imagen procesados: {procesados}. "
            f"Nuevo punto de control: {id_mas_reciente}"
        )

    except Exception as error:
        print(f"[ERROR] Fallo inesperado en el lote: {error}")
    finally:
        # IMPRESCINDIBLE: cerrar para que el proceso termine y el
        # GitHub Action no se quede colgado consumiendo minutos.
        await client.close()


if __name__ == "__main__":
    asyncio.run(client.start(DISCORD_TOKEN))
