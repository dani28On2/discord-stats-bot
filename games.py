"""
games.py
========
CONFIGURACIÓN DE JUEGOS.

Este es el ÚNICO archivo que tienes que tocar para añadir o quitar juegos.
Cada juego se describe con:

  - display_name: cómo aparece en los mensajes del bot.
  - channel:      nombre EXACTO del canal de Discord (sin "#").
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
                              confirmaciones (ej: '💵', '💰').
                    - title:  título del mensaje fijado de esa stat
                              (ej: 'MOST CASH'). Se muestra en grande.
  - top_size:     cuántos jugadores muestra el mensaje fijado.

Para añadir un juego nuevo: copia un bloque y modifícalo.
"""

# Los sufijos vienen del juego (Verse: STRING_Abbrev). Mantener este
# texto sincronizado con formatting.ABBREV.
SUFIJOS_DEL_JUEGO = (
    "K, M, B, T, Qa, Qi, Sx, Sp, Oc, No, Dc, Un, Du, Tr, "
    "Qt, Qn, Se, St, Og, Nn, Vg, UVg"
)


GAMES: dict[str, dict] = {
    # ------------------------------------------------------------------
    # KICK A LUCKY BLOCK
    # ------------------------------------------------------------------
    "kick_a_lucky_block": {
        "display_name": "Kick A Lucky Block",
        "channel": "〔📋〕kick-leaderboard",
        "player_name_description": (
            "Texto blanco que aparece debajo de la imagen de perfil "
            "(avatar) del jugador."
        ),
        "stats": {
            "income": {
                "desc": (
                    "Número AMARILLO que representa el dinero por segundo "
                    "del jugador. Se reconoce porque lleva el símbolo "
                    "'$' delante y termina en '/s' (ejemplo: '$1.2K/s', "
                    f"'$45.7Qa/s'). Sufijos posibles: {SUFIJOS_DEL_JUEGO}."
                ),
                "format": "income",   # -> '$1.2Qa/s'
                "emoji": "💰",
                "title": "MOST INCOME",
            },
            "cash": {
                "desc": (
                    "Número VERDE con el símbolo '$' delante, situado en "
                    "la barra inferior. Es el dinero total acumulado del "
                    "jugador (ejemplo: '$45.7M', '$1.2Qa'). "
                    f"Sufijos posibles: {SUFIJOS_DEL_JUEGO}."
                ),
                "format": "money",    # -> '$1.2Qa'
                "emoji": "💵",
                "title": "MOST CASH",
            },
        },
        "top_size": 10,
    },

    # ------------------------------------------------------------------
    # PLANTILLA PARA AÑADIR UN JUEGO NUEVO  (copia y modifica)
    # ------------------------------------------------------------------
    # "mi_juego": {
    #     "display_name": "Mi Juego",
    #     "channel": "mi-juego-leaderboard",
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
