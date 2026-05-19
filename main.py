"""
main.py
=======
Punto de entrada del bot.

Flujo:
  1. Escucha mensajes SOLO en el canal configurado (#subir-stats).
  2. Si el mensaje trae una imagen adjunta, descarga sus bytes.
  3. Envía la imagen a Gemini y obtiene un JSON validado.
  4. Guarda en Supabase la mejor puntuación del jugador.
  5. Responde con un mensaje amigable en el canal.

Ejecutar con:  python main.py
"""

import discord

from src.config import DISCORD_TOKEN, TARGET_CHANNEL_NAME
from src.database import guardar_puntuacion
from src.gemini_service import extract_stats_from_image

# --- Configuración de intents ---
# message_content es OBLIGATORIO para poder leer adjuntos y texto.
# Acuérdate de activarlo también en el portal de desarrolladores:
#   Tu App > Bot > Privileged Gateway Intents > MESSAGE CONTENT INTENT
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    """Se ejecuta una vez cuando el bot se conecta correctamente."""
    print(f"[BOT] Conectado como {client.user}")
    print(f"[BOT] Escuchando el canal: #{TARGET_CHANNEL_NAME}")


@client.event
async def on_message(message: discord.Message):
    """Se ejecuta con cada mensaje que el bot puede ver."""

    # 1) Ignorar los mensajes del propio bot (evita bucles infinitos).
    if message.author == client.user:
        return

    # 2) Procesar solo el canal objetivo. (channel.name puede ser None
    #    en DMs, por eso usamos getattr con valor por defecto).
    if getattr(message.channel, "name", None) != TARGET_CHANNEL_NAME:
        return

    # 3) Si no hay adjuntos, no hay nada que analizar.
    if not message.attachments:
        return

    attachment = message.attachments[0]

    # 4) Verificar que el adjunto sea realmente una imagen.
    if not (attachment.content_type or "").startswith("image/"):
        await message.reply(
            "⚠️ Eso no parece una imagen. Sube una **captura de pantalla** "
            "de la pantalla de resultados."
        )
        return

    # Indicador "escribiendo..." mientras procesamos (mejor UX).
    async with message.channel.typing():

        # 5) Descargar la imagen y mandarla a Gemini.
        try:
            image_bytes = await attachment.read()
            stats = await extract_stats_from_image(
                image_bytes, attachment.content_type
            )
        except Exception as error:
            print(f"[ERROR] Fallo al analizar la imagen con Gemini: {error}")
            await message.reply(
                "❌ No pude analizar la imagen. Inténtalo de nuevo en un "
                "momento o sube otra captura."
            )
            return

        # 6) Validación de negocio: ¿Gemini leyó datos fiables?
        if not stats.stats_detected or stats.score <= 0:
            await message.reply(
                "🔍 No conseguí leer las estadísticas. Asegúrate de que la "
                "captura **no esté borrosa** y de que se vean claramente la "
                "puntuación y las bajas."
            )
            return

        # 7) Guardar en Supabase.
        try:
            resultado = await guardar_puntuacion(
                discord_id=str(message.author.id),
                username=str(message.author),
                score=stats.score,
                kills=stats.kills,
            )
        except Exception as error:
            print(f"[ERROR] Fallo al guardar en Supabase: {error}")
            await message.reply(
                "❌ Leí tus stats pero hubo un problema al guardarlas en la "
                "base de datos. Avisa a un administrador."
            )
            return

    # 8) Mensaje de confirmación según lo que ocurrió.
    jugador = stats.player_name or message.author.display_name
    estado = resultado["estado"]

    if estado == "creado":
        await message.reply(
            f"✅ ¡Bienvenido al ranking, **{jugador}**! "
            f"Puntuación de **{stats.score:,}** registrada con éxito "
            f"({stats.kills} bajas)."
        )
    elif estado == "actualizado":
        await message.reply(
            f"🏆 ¡Nuevo récord, **{jugador}**! "
            f"**{stats.score:,}** puntos (antes: "
            f"{resultado['record_previo']:,}). ¡A seguir así!"
        )
    else:  # "sin_cambios"
        await message.reply(
            f"📊 Registrado, pero tu mejor marca sigue siendo "
            f"**{resultado['puntuacion']:,}**. ¡La próxima la superas!"
        )


if __name__ == "__main__":
    # client.run() gestiona el bucle de eventos y la reconexión.
    client.run(DISCORD_TOKEN)
