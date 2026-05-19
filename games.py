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
                  en la captura. Es común a todas las stats del juego.
  - stats:        diccionario {clave_interna: descripcion_para_gemini}.
                  La clave interna es la que se guarda en la base de
                  datos. La descripción debe ser PRECISA: cuanto mejor
                  describas qué tiene que mirar Gemini, menos errores.
  - top_size:     cuántos jugadores muestra el mensaje fijado de esa
                  stat (por defecto 10).

Para añadir un juego nuevo: copia un bloque, cámbiale los valores y haz
push. La base de datos y el bot lo recogen automáticamente.
"""

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
            "income": (
                "Número AMARILLO que representa el dinero por segundo "
                "del jugador. Se reconoce porque lleva el símbolo '$' "
                "delante y termina en '/s' (por ejemplo: '$1.2K/s'). "
                "Si la cifra tiene sufijo de magnitud (K, M, B, T), "
                "conviértela al entero correspondiente "
                "(K=mil, M=millón, B=mil millones, T=billón)."
            ),
            "cash": (
                "Número VERDE con el símbolo '$' delante, situado en "
                "la barra inferior. Es el dinero total acumulado del "
                "jugador. Si la cifra tiene sufijo de magnitud (K, M, "
                "B, T), conviértela al entero correspondiente."
            ),
        },
        "top_size": 10,
    },

    # ------------------------------------------------------------------
    # PLANTILLA PARA AÑADIR UN JUEGO NUEVO  (copia y modifica)
    # ------------------------------------------------------------------
    # "mi_juego": {
    #     "display_name": "Mi Juego",
    #     "channel": "mi-juego-leaderboard",
    #     "player_name_description": "Texto blanco con el nick, arriba a la izquierda",
    #     "stats": {
    #         "kills": "Número rojo grande junto al icono de calavera",
    #         "score": "Número amarillo en el centro, debajo de 'SCORE'",
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
