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
import io
import json
from datetime import datetime

import discord

from config import DISCORD_TOKEN
from database import (
    guardar_stat,
    guardar_ultimo_mensaje,
    guardar_id_pinned,
    guardar_id_resumen,
    obtener_id_pinned,
    obtener_id_resumen,
    obtener_top,
    obtener_ultimo_mensaje,
)
from formatting import format_value, parse_abbrev
from games import GAMES, get_game_by_channel
from gemini_service import extract_stats_from_image

# Cuando un juego se procesa por primera vez, no inundamos el canal con
# confirmaciones del historial entero: solo miramos los últimos N.
BACKFILL_PRIMERA_VEZ = 25

# Tope de mensajes nuevos por ejecución (evita tandas inesperadas).
MAX_POR_EJECUCION = 200

# Mensaje único de rechazo (imagen ilegible o no es una stats card).
# Se usa tanto cuando Gemini marca stats_detected=false como cuando
# Gemini detecta la card pero no consigue leer ningún valor > 0.
REJECTION_MESSAGE = (
    "❌ This image was rejected — please resubmit.\n"
    "**Reason:** Not a valid stats card.\n"
    "Your screenshot must clearly show the statistics card, "
    "including the island code at the bottom."
)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------
def _es_imagen(att: discord.Attachment) -> bool:
    return (att.content_type or "").startswith("image/")


def _normalizar_codigo(texto: str) -> str:
    """
    Deja solo los dígitos de un código de isla, para comparar el número
    sin que importen guiones o espacios.
    '(2943-6452-4033)' -> '294364524033'
    """
    return "".join(c for c in str(texto or "") if c.isdigit())


def _tiene_parentesis(texto: str) -> bool:
    """
    True si el texto contiene un par de paréntesis con dígitos dentro.
    El código de isla legítimo SIEMPRE aparece entre paréntesis, así que
    esto descarta otros números de la pantalla que no los lleven.
    """
    s = str(texto or "")
    abre = s.find("(")
    cierra = s.find(")", abre + 1)
    if abre == -1 or cierra == -1:
        return False
    # Que haya al menos un dígito dentro de los paréntesis.
    return any(c.isdigit() for c in s[abre + 1 : cierra])


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
        await message.reply(REJECTION_MESSAGE, mention_author=False)
        return

    # 1.5) Verificar el código de isla: la captura debe pertenecer a
    #      este juego. Exigimos (a) que venga entre paréntesis y (b) que
    #      los dígitos coincidan con el código del juego. Los guiones o
    #      espacios internos no importan (tolerancia al OCR).
    esperado = _normalizar_codigo(game_config.get("island_code", ""))
    if esperado:  # solo validamos si el juego tiene código configurado
        crudo = stats.get("island_code", "")
        leido = _normalizar_codigo(crudo)
        if not _tiene_parentesis(crudo) or leido != esperado:
            print(
                f"[INFO] {game_key} / msg {message.id}: código de isla "
                f"inválido (leído '{crudo or 'vacío'}', "
                f"esperado entre paréntesis '{game_config['island_code']}'). "
                f"Rechazada."
            )
            await message.reply(REJECTION_MESSAGE, mention_author=False)
            return

    # 2) Guardar cada stat por separado y construir el resumen para Discord.
    jugador = stats.get("player_name") or message.author.display_name
    es_vip = bool(stats.get("is_vip", False))
    lineas_resumen: list[str] = []

    for stat_key, stat_info in game_config["stats"].items():
        # Gemini devuelve algo como '1.2Qa' -> lo pasamos a entero exacto.
        valor_crudo = stats.get(stat_key, "")
        valor = parse_abbrev(valor_crudo)
        if valor <= 0:
            # No guardamos ceros: Gemini probablemente no pudo leer esa
            # stat. Las otras pueden seguir siendo válidas.
            continue

        try:
            resultado = await guardar_stat(
                game=game_key,
                discord_id=str(message.author.id),
                username=str(message.author),
                stat=stat_key,
                value=valor,
                is_vip=es_vip,
            )
        except Exception as error:
            print(f"[ERROR] {game_key}/{stat_key}: fallo al guardar: {error}")
            continue

        fmt = stat_info.get("format", "raw") if isinstance(stat_info, dict) else "raw"
        emoji = stat_info.get("emoji", "📊") if isinstance(stat_info, dict) else "📊"
        valor_fmt = format_value(valor, fmt)

        estado = resultado["estado"]
        if estado == "actualizado":
            previo_fmt = format_value(resultado["record_previo"], fmt)
            lineas_resumen.append(
                f"{emoji} **{stat_key}**: {valor_fmt} (previous {previo_fmt})"
            )
        elif estado == "creado":
            lineas_resumen.append(
                f"{emoji} **{stat_key}**: {valor_fmt} (first record)"
            )
        else:  # sin_cambios
            tu_record_fmt = format_value(resultado["valor"], fmt)
            lineas_resumen.append(
                f"{emoji} **{stat_key}**: {valor_fmt} "
                f"(your record stays at {tu_record_fmt})"
            )

    if not lineas_resumen:
        await message.reply(REJECTION_MESSAGE, mention_author=False)
        return

    cabecera = f"🎯 **{jugador}**'s screenshot processed"
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
    medallas = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    stat_info = game_config["stats"][stat_key]
    fmt = stat_info.get("format", "raw") if isinstance(stat_info, dict) else "raw"
    emoji = stat_info.get("emoji", "📊") if isinstance(stat_info, dict) else "📊"
    titulo_stat = (
        stat_info.get("title", stat_key.upper())
        if isinstance(stat_info, dict)
        else stat_key.upper()
    )

    if not top:
        cuerpo = "_Aún no hay registros para esta estadística._"
    else:
        lineas = []
        for i, fila in enumerate(top):
            medalla = medallas[i] if i < len(medallas) else "▫️"
            valor = format_value(int(fila["best_value"]), fmt)
            lineas.append(f"{medalla} **{fila['username']}** — {valor}")
        cuerpo = "\n".join(lineas)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    # '# ' al principio = título grande en Discord (markdown).
    return (
        f"# {emoji} {titulo_stat} {emoji}\n\n"
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
# Mensaje resumen consolidado (canal de moderadores)
# ---------------------------------------------------------------------
def _construir_json(game_key: str, game_config: dict, datos: dict) -> str:
    """
    Construye el texto JSON consolidado de un juego.

    `datos` es {stat_key: [filas_top...]} ya obtenido de la BD.
    Estructura del JSON resultante:
        {
          "game": "Laser For Brainrots",
          "updated_at": "2026-05-28 12:00 UTC",
          "leaderboards": {
            "income": [ {"name": "...", "income": "$7.8T/s"}, ... ],
            "cash":   [ {"name": "...", "cash": "$677.8T"}, ... ]
          }
        }
    El valor va FORMATEADO como se ve en el juego ($, sufijo, /s).
    """
    leaderboards = {}
    for stat_key, top in datos.items():
        stat_info = game_config["stats"][stat_key]
        fmt = stat_info.get("format", "raw") if isinstance(stat_info, dict) else "raw"
        leaderboards[stat_key] = [
            {
                "name": fila["username"],
                stat_key: format_value(int(fila["best_value"]), fmt),
                "isVip": bool(fila.get("is_vip", False)),
            }
            for fila in top
        ]

    documento = {
        "game": game_config["display_name"],
        "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "leaderboards": leaderboards,
    }
    return json.dumps(documento, indent=2, ensure_ascii=False)


async def _actualizar_mensaje_resumen(
    canal_resumen: discord.TextChannel, game_key: str, game_config: dict
) -> None:
    """
    Publica el resumen del juego como ARCHIVO .json adjunto.

    Discord no permite editar un archivo adjunto ya enviado, así que el
    patrón es: borrar el mensaje anterior (si existe) y enviar uno nuevo
    con el archivo actualizado. El ID del nuevo mensaje se guarda para
    poder borrarlo en la siguiente ejecución.
    """
    # 1) Reunir los datos de todas las stats.
    datos = {}
    for stat_key in game_config["stats"]:
        datos[stat_key] = await obtener_top(
            game_key, stat_key, limit=game_config["top_size"]
        )

    contenido_json = _construir_json(game_key, game_config, datos)

    # 2) Borrar el mensaje anterior si lo había.
    msg_id = await obtener_id_resumen(game_key)
    if msg_id is not None:
        try:
            anterior = await canal_resumen.fetch_message(int(msg_id))
            await anterior.delete()
        except discord.NotFound:
            pass  # ya no existía, seguimos
        except discord.HTTPException as e:
            print(f"[WARN] No pude borrar el resumen anterior de {game_key}: {e}")

    # 3) Enviar el nuevo con el archivo adjunto.
    #    El archivo se construye en memoria, sin tocar disco.
    nombre_archivo = f"{game_key}_leaderboard.json"
    archivo = discord.File(
        io.BytesIO(contenido_json.encode("utf-8")),
        filename=nombre_archivo,
    )
    mensaje_texto = (
        f"**{game_config['display_name']}** — leaderboard\n"
        f"_Actualizado: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_"
    )
    try:
        nuevo = await canal_resumen.send(content=mensaje_texto, file=archivo)
        await guardar_id_resumen(game_key, str(nuevo.id))
    except discord.HTTPException as e:
        print(f"[ERROR] No pude enviar el resumen de {game_key}: {e}")


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
# Resolución de canales por nombre, con detección de duplicados
# ---------------------------------------------------------------------
def _resolver_canal(
    todos: list[discord.TextChannel], nombre: str
) -> tuple[discord.TextChannel | None, str | None]:
    """
    Devuelve (canal, error). Si hay varios canales con el mismo nombre,
    no adivina: devuelve error. Si no existe, devuelve (None, None).
    """
    coincidencias = [ch for ch in todos if ch.name == nombre]
    if len(coincidencias) == 0:
        return None, None
    if len(coincidencias) > 1:
        ids = ", ".join(str(ch.id) for ch in coincidencias)
        return None, (
            f"Hay {len(coincidencias)} canales llamados #{nombre} "
            f"(IDs: {ids}). Renómbralos o pásate a IDs en games.py."
        )
    return coincidencias[0], None


# ---------------------------------------------------------------------
# on_ready: orquesta todo y cierra
# ---------------------------------------------------------------------
@client.event
async def on_ready():
    print(f"[BATCH] Conectado como {client.user}")
    try:
        # Lista única de canales de texto, ordenable por nombre con duplicados.
        canales_texto: list[discord.TextChannel] = [
            ch for ch in client.get_all_channels()
            if isinstance(ch, discord.TextChannel)
        ]

        # Cache para no resolver el mismo canal resumen una vez por juego.
        cache_resumen: dict[str, discord.TextChannel | None] = {}

        for game_key, game_config in GAMES.items():
            # --- 1) Canal del juego ---
            nombre_canal = game_config["channel"]
            canal, err = _resolver_canal(canales_texto, nombre_canal)
            if err:
                print(f"[ERROR] {game_key}: {err}")
                continue
            if canal is None:
                print(
                    f"[ERROR] El juego '{game_key}' apunta al canal "
                    f"#{nombre_canal}, pero no lo encuentro. ¿Existe y "
                    f"tiene el bot permiso de verlo?"
                )
                continue

            permisos = canal.permissions_for(canal.guild.me)
            if not permisos.manage_messages:
                print(
                    f"[WARN] No tengo permiso 'Manage Messages' en "
                    f"#{nombre_canal}; no podré fijar el Top."
                )

            # --- 2) Procesar capturas y refrescar pinned por stat ---
            try:
                await _procesar_juego(canal, game_key)
            except Exception as e:
                print(f"[ERROR] Fallo procesando '{game_key}': {e}")
                # Aun así intentamos publicar el resumen abajo.

            # --- 3) Mensaje resumen en el canal de moderadores ---
            nombre_resumen = game_config.get("summary_channel")
            if not nombre_resumen:
                continue

            if nombre_resumen not in cache_resumen:
                canal_resumen, err = _resolver_canal(canales_texto, nombre_resumen)
                if err:
                    print(f"[ERROR] Canal resumen '{nombre_resumen}': {err}")
                    cache_resumen[nombre_resumen] = None
                elif canal_resumen is None:
                    print(
                        f"[ERROR] No encuentro el canal resumen "
                        f"#{nombre_resumen}. Créalo o quita "
                        f"'summary_channel' de games.py para deshabilitarlo."
                    )
                    cache_resumen[nombre_resumen] = None
                else:
                    # El bot necesita Attach Files (para el .json) y
                    # Manage Messages (para borrar el resumen anterior).
                    p = canal_resumen.permissions_for(canal_resumen.guild.me)
                    if not p.attach_files:
                        print(
                            f"[WARN] Sin permiso 'Attach Files' en "
                            f"#{nombre_resumen}: no podré subir el .json."
                        )
                    if not p.manage_messages:
                        print(
                            f"[WARN] Sin permiso 'Manage Messages' en "
                            f"#{nombre_resumen}: no podré borrar el resumen "
                            f"anterior (se acumularán mensajes)."
                        )
                    cache_resumen[nombre_resumen] = canal_resumen

            canal_resumen = cache_resumen[nombre_resumen]
            if canal_resumen is None:
                continue

            try:
                await _actualizar_mensaje_resumen(canal_resumen, game_key, game_config)
            except Exception as e:
                print(f"[ERROR] Fallo publicando resumen de '{game_key}': {e}")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(client.start(DISCORD_TOKEN))
