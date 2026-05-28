"""
games.py
========
CONFIGURACIÓN DE JUEGOS.

Este es el ÚNICO archivo que tienes que tocar para añadir o quitar juegos.
Cada juego se describe con:

  - display_name: cómo aparece en los mensajes del bot.
  - channel:      nombre EXACTO del canal de Discord donde los jugadores
                  suben sus capturas (sin "#"). El bot lee mensajes nuevos
                  de aquí y publica los mensajes fijados de Top N por stat.
  - summary_channel:
                  nombre del canal (también sin "#") donde el bot
                  mantiene UN mensaje consolidado por juego con todas
                  las tablas dentro. Usado como respaldo / referencia
                  para moderadores. Puede ser el mismo nombre en varios
                  juegos: cada juego tendrá su mensaje editable propio.
  - player_name_description:
                  pista para Gemini sobre cómo es el nombre del jugador
                  en la captura.
  - stats:        diccionario {clave_interna: {desc, format, emoji, title}}
                    - desc:   descripción visual para Gemini.
                    - format: cómo se MUESTRA el valor en Discord.
                              Disponibles (ver formatting.py):
                                'money'  -> '$1.2Qa'
                                'income' -> '$1.2Qa/s'
                                'plain'  -> '1.2Qa'  (sin símbolo)
                                'raw'    -> '1,200,000'  (entero plano)
                    - emoji:  emoji que precede a la stat en las
                              confirmaciones y abre/cierra el título
                              del mensaje fijado.
                    - title:  título del mensaje fijado de esa stat
                              (ej: 'MOST CASH').
  - top_size:     cuántos jugadores muestra cada ranking.

Para añadir un juego nuevo: copia un bloque y modifícalo.
"""

# Los sufijos vienen del juego (Verse: STRING_Abbrev). Mantener este
# texto sincronizado con formatting.ABBREV.
SUFIJOS_DEL_JUEGO = (
    "K, M, B, T, Qa, Qi, Sx, Sp, Oc, No, Dc, Un, Du, Tr, "
    "Qt, Qn, Se, St, Og, Nn, Vg, UVg"
)

# Las stats de income y cash se reusan entre juegos (de momento son
# iguales). Las defino una vez y las inserto en cada juego que las use.
STATS_INCOME_CASH = {
    "income": {
        "desc": (
            "Número AMARILLO que representa el dinero por segundo del "
            "jugador. Se reconoce porque lleva el símbolo '$' delante y "
            "termina en '/s' (ejemplo: '$1.2K/s', '$45.7Qa/s'). "
            f"Sufijos posibles: {SUFIJOS_DEL_JUEGO}."
        ),
        "format": "income",
        "emoji": "💰",
        "title": "MOST INCOME",
    },
    "cash": {
        "desc": (
            "Número VERDE con el símbolo '$' delante, situado en la "
            "barra inferior. Es el dinero total acumulado del jugador "
            "(ejemplo: '$45.7M', '$1.2Qa'). "
            f"Sufijos posibles: {SUFIJOS_DEL_JUEGO}."
        ),
        "format": "money",
        "emoji": "💵",
        "title": "MOST CASH",
    },
}

# Descripción común del nombre del jugador (mismo formato en ambos juegos).
NOMBRE_JUGADOR_DESC = (
    "Texto blanco que aparece debajo de la imagen de perfil (avatar) "
    "del jugador."
)

# Canal único de respaldo/referencia para moderadores.
# OJO: el carácter entre el emoji y el texto es '︱' (U+FE31), NO un '|'
# normal. Si renombras el canal en Discord, copia y pega el nombre tal cual
# en lugar de teclearlo.
CANAL_RESUMEN = "📊︱leaderboard-data"


GAMES: dict[str, dict] = {
    # ------------------------------------------------------------------
    # LASER FOR BRAINROTS
    # ------------------------------------------------------------------
    "laser_for_brainrots": {
        "display_name": "Laser For Brainrots",
        "channel": "laser-for-brainrots",
        "summary_channel": CANAL_RESUMEN,
        "player_name_description": NOMBRE_JUGADOR_DESC,
        "stats": STATS_INCOME_CASH,
        "top_size": 10,
    },

    # ------------------------------------------------------------------
    # BE FLASH FOR BRAINROTS
    # ------------------------------------------------------------------
    "be_flash_for_brainrots": {
        "display_name": "Be Flash For Brainrots",
        "channel": "be-flash-for-brainrots",
        "summary_channel": CANAL_RESUMEN,
        "player_name_description": NOMBRE_JUGADOR_DESC,
        "stats": STATS_INCOME_CASH,
        "top_size": 10,
    },

    # ------------------------------------------------------------------
    # PLANTILLA PARA AÑADIR UN JUEGO NUEVO  (copia y modifica)
    # ------------------------------------------------------------------
    # "mi_juego": {
    #     "display_name": "Mi Juego",
    #     "channel": "mi-juego",
    #     "summary_channel": CANAL_RESUMEN,
    #     "player_name_description": "...",
    #     "stats": {
    #         "kills": {
    #             "desc": "Número rojo junto al icono de calavera",
    #             "format": "raw",
    #             "emoji": "💀",
    #             "title": "MOST KILLS",
    #         },
    #     },
    #     "top_size": 10,
    # },
}


def get_game_by_channel(channel_name: str) -> tuple[str, dict] | None:
    """Devuelve (clave_interna, config) del juego asociado a ese canal."""
    for key, cfg in GAMES.items():
        if cfg["channel"] == channel_name:
            return key, cfg
    return None
