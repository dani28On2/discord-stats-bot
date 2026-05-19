"""
batch_update.py
================
Bot por LOTES, multi-juego.

Cada ejecución (manual desde GitHub Actions o por cron) hace, POR CADA
juego declarado en games.py:

  1. Localiza su canal de Discord.
  2. Lee mensajes nuevos desde el último procesado (guardado en Supabase).
  3. Por cada captura nueva:
       - Construye un esquema Pydantic específico del juego.
       - Manda imagen + esquema + prompt a Gemini.
       - Guarda en la base de datos la MEJOR marca del jugador en cada
         estadística (cada stat tiene su récord independiente).
       - Responde en hilo con la confirmación.
  4. Actualiza UN mensaje FIJADO por cada stat con el Top 10 actual.
     Si no existe, lo crea y lo fija.

Al terminar cierra la conexión: el GitHub Action se cierra solo.
"""

import asyncio
from datetime import datetime

import discord

from config import DISCORD_TOKEN
from database import (
    guardar_stat,
    guardar_ultimo_mensaje,
    guardar_id_pinned,
    obtener_id_pinned,
    obtener_top,
    obtener_ultimo_mensaje,
)
from games import GAMES, get_game_by_channel
from gemini_service import extract_stats_from_image

# Cuando un juego se procesa por primera vez, no inundamos el canal con
# confirmaciones del historial entero: solo miramos los últimos N.
BACKFILL_PRIMERA_VEZ = 25

# Tope de mensajes nuevos por ejecución (evita tandas inesperadas).
MAX_POR_EJECUCION = 200

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


# ---------------------------------------------------------------------
# Utilidades de formato
# ---------------------------------------------------------------------
def _formatear_numero(n: int) -> str:
    """1500 -> '1,500'. Solo cosmético para los mensajes."""
    return f"{n:,}"


def _es_imagen(att: discord.Attachment) -> bool:
    return (att.content_type or "").startswith("image/")


# ---------------------------------------------------------------------
# Procesado de UN mensaje con captura
# ---------------------------------------------------------------------
async def _procesar_mensaje(
    message: discord.Message, game_key: str, game_config: dict
) -> None:
    attachment = message.attachments[0]
    if not _es_imagen(attachment):
        return

    # 1) Gemini lee la captura con el esquema propio del juego.
    try:
        image_bytes = await attachment.read()
        stats = await extract_stats_from_image(
            image_bytes, attachment.content_type, game_config
        )
        print(f"[DEBUG] {game_key} / msg {message.id}: {stats}")
    except Exception as error:
        print(f"[WARN] {game_key} / msg {message.id}: error en Gemini: {error}")
        return

    if not stats.get("stats_detected"):
        await message.reply(
            "🔍 No conseguí leer las estadísticas de esta captura "
            "(¿borrosa o sin datos visibles?).",
            mention_author=False,
        )
        return

    # 2) Guardar cada stat por separado y construir el resumen para Discord.
    jugador = stats.get("player_name") or message.author.display_name
    lineas_resumen: list[str] = []
    nuevo_record = False

    for stat_key in game_config["stats"]:
        valor = int(stats.get(stat_key, 0) or 0)
        if valor <= 0:
            # No guardamos ceros: probablemente Gemini no pudo leer
            # esa stat concreta. Las demás sí pueden valer.
            continue

        try:
            resultado = await guardar_stat(
                game=game_key,
                discord_id=str(message.author.id),
                username=str(message.author),
                stat=stat_key,
                value=valor,
            )
        except Exception as error:
            print(f"[ERROR] {game_key}/{stat_key}: fallo al guardar: {error}")
            continue

        estado = resultado["estado"]
        if estado == "actualizado":
            nuevo_record = True
            lineas_resumen.append(
                f"🏆 **{stat_key}**: {_formatear_numero(valor)} "
                f"(antes {_formatear_numero(resultado['record_previo'])})"
            )
        elif estado == "creado":
            nuevo_record = True
            lineas_resumen.append(
                f"✨ **{stat_key}**: {_formatear_numero(valor)} (primer registro)"
            )
        else:  # sin_cambios
            lineas_resumen.append(
                f"• **{stat_key}**: {_formatear_numero(valor)} "
                f"(tu récord sigue siendo {_formatear_numero(resultado['valor'])})"
            )

    if not lineas_resumen:
        await message.reply(
            "⚠️ No pude leer ninguna estadística de la captura.",
            mention_author=False,
        )
        return

    cabecera = (
        f"🎯 Captura de **{jugador}** procesada"
        + (" — ¡nuevo récord! 🎉" if nuevo_record else "")
    )
    await message.reply(
        cabecera + "\n" + "\n".join(lineas_resumen),
        mention_author=False,
    )


# ---------------------------------------------------------------------
# Mensaje fijado del Top 10 (uno por stat)
# ---------------------------------------------------------------------
def _formatear_top(
    game_config: dict, stat_key: str, top: list[dict]
) -> str:
    """Construye el texto del mensaje fijado para una stat."""
    nombre_juego = game_config["display_name"]
    medallas = ["🥇", "🥈", "🥉"] + ["🏅"] * 7

    if not top:
        cuerpo = "_Aún no hay registros para esta estadística._"
    else:
        lineas = []
        for i, fila in enumerate(top):
            medalla = medallas[i] if i < len(medallas) else "▫️"
            valor = _formatear_numero(int(fila["best_value"]))
            lineas.append(f"{medalla} **{fila['username']}** — {valor}")
        cuerpo = "\n".join(lineas)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"📌 **{nombre_juego} — Top {game_config['top_size']} · "
        f"`{stat_key}`**\n\n"
        f"{cuerpo}\n\n"
        f"_Actualizado: {timestamp}_"
    )


async def _actualizar_mensaje_fijado(
    canal: discord.TextChannel, game_key: str, game_config: dict, stat_key: str
) -> None:
    """Crea o edita el mensaje fijado del Top de una stat."""
    top = await obtener_top(game_key, stat_key, limit=game_config["top_size"])
    texto = _formatear_top(game_config, stat_key, top)

    msg_id = await obtener_id_pinned(game_key, stat_key)

    # Intentar editar el mensaje existente.
    if msg_id is not None:
        try:
            mensaje = await canal.fetch_message(int(msg_id))
            await mensaje.edit(content=texto)
            if not mensaje.pinned:
                try:
                    await mensaje.pin(reason="Leaderboard auto-pin")
                except discord.HTTPException as e:
                    print(f"[WARN] No pude fijar {game_key}/{stat_key}: {e}")
            return
        except discord.NotFound:
            # El mensaje fue borrado: caemos al flujo de creación.
            print(
                f"[INFO] El mensaje fijado de {game_key}/{stat_key} "
                f"ya no existe. Lo recreo."
            )
        except discord.HTTPException as e:
            print(f"[WARN] Error editando {game_key}/{stat_key}: {e}")
            return

    # Crear y fijar uno nuevo.
    try:
        nuevo = await canal.send(texto)
        try:
            await nuevo.pin(reason="Leaderboard auto-pin")
        except discord.HTTPException as e:
            # Si no puede fijar (límite de 50 o falta de permiso),
            # al menos guardamos el ID y lo editaremos sin pin.
            print(f"[WARN] Creado pero no fijado {game_key}/{stat_key}: {e}")
        await guardar_id_pinned(game_key, stat_key, str(nuevo.id))
    except discord.HTTPException as e:
        print(f"[ERROR] No pude crear el mensaje del Top {game_key}/{stat_key}: {e}")


# ---------------------------------------------------------------------
# Procesado de UN juego completo (un canal)
# ---------------------------------------------------------------------
async def _procesar_juego(canal: discord.TextChannel, game_key: str) -> None:
    game_config = GAMES[game_key]
    print(f"\n[BATCH] === {game_config['display_name']} (#{canal.name}) ===")

    # 1) Mensajes nuevos desde el último procesado.
    ultimo_id = await obtener_ultimo_mensaje(game_key)
    if ultimo_id is None:
        print(f"[BATCH] Primera ejecución: últimos {BACKFILL_PRIMERA_VEZ} mensajes.")
        recientes = [
            m async for m in canal.history(
                limit=BACKFILL_PRIMERA_VEZ, oldest_first=False
            )
        ]
        mensajes = list(reversed(recientes))
    else:
        despues_de = discord.Object(id=int(ultimo_id))
        mensajes = [
            m async for m in canal.history(
                limit=MAX_POR_EJECUCION, after=despues_de, oldest_first=True
            )
        ]

    # 2) Procesar los que sean del usuario y traigan imagen.
    procesados = 0
    if mensajes:
        for message in mensajes:
            if message.author == client.user:
                continue
            if not message.attachments:
                continue
            await _procesar_mensaje(message, game_key, game_config)
            procesados += 1

        # Avanzar puntero aunque alguno falle (no nos quedamos atrapados).
        id_mas_reciente = max(m.id for m in mensajes)
        await guardar_ultimo_mensaje(game_key, str(id_mas_reciente))
        print(
            f"[BATCH] {game_key}: {procesados} capturas procesadas. "
            f"Puntero -> {id_mas_reciente}"
        )
    else:
        print(f"[BATCH] {game_key}: no hay mensajes nuevos.")

    # 3) Refrescar los mensajes fijados de cada stat (aunque no haya
    #    habido capturas: si los borraron, los volvemos a crear).
    for stat_key in game_config["stats"]:
        await _actualizar_mensaje_fijado(canal, game_key, game_config, stat_key)


# ---------------------------------------------------------------------
# on_ready: orquesta todo y cierra
# ---------------------------------------------------------------------
@client.event
async def on_ready():
    print(f"[BATCH] Conectado como {client.user}")
    try:
        # Mapear nombre de canal -> objeto canal una sola vez.
        canales_por_nombre = {
            ch.name: ch
            for ch in client.get_all_channels()
            if isinstance(ch, discord.TextChannel)
        }

        for game_key, game_config in GAMES.items():
            nombre_canal = game_config["channel"]
            canal = canales_por_nombre.get(nombre_canal)
            if canal is None:
                print(
                    f"[ERROR] El juego '{game_key}' apunta al canal "
                    f"#{nombre_canal}, pero no lo encuentro. ¿Existe y "
                    f"tiene el bot permiso de verlo?"
                )
                continue

            # Verificación útil: el bot necesita poder fijar mensajes.
            permisos = canal.permissions_for(canal.guild.me)
            if not permisos.manage_messages:
                print(
                    f"[WARN] No tengo permiso 'Manage Messages' en "
                    f"#{nombre_canal}; no podré fijar el Top. Dame ese "
                    f"permiso en la configuración del canal."
                )

            try:
                await _procesar_juego(canal, game_key)
            except Exception as e:
                print(f"[ERROR] Fallo procesando '{game_key}': {e}")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(client.start(DISCORD_TOKEN))
