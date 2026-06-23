"""
gemini_service.py
=================
Habla con la API de Gemini.

ARQUITECTURA SIMPLIFICADA (un solo canal de envío):
Como ahora todas las capturas llegan por un canal único y el juego se
identifica DESPUÉS leyendo el código de isla de la imagen, ya no podemos
construir el esquema "para el juego X" antes de la llamada.

Solución: construimos un esquema UNIVERSAL que pide las stats de TODOS
los juegos configurados (income, cash, etc.). Como en tu caso todos
comparten income+cash, una sola llamada cubre cualquier juego.

Una llamada típica devuelve:
    {
      "stats_detected": True,
      "player_name": "skibidi boy",
      "island_code": "(2943-6452-4033)",
      "is_vip": False,
      "income": "1.2K",
      "cash": "45M"
    }

El bot identifica el juego a partir de "island_code" y se queda solo con
las stats relevantes para ese juego.
"""

import asyncio
import random

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, create_model

from config import GEMINI_API_KEY, GEMINI_MODEL
from games import GAMES, ISLAND_CODE_DESC, NOMBRE_JUGADOR_DESC

_client = genai.Client(api_key=GEMINI_API_KEY)

# --- Configuración de reintentos ---
# Reintentamos sólo errores TRANSITORIOS (no fallos de la imagen ni de
# nuestro código). Estos códigos son los que documenta Google:
#   429 -> RESOURCE_EXHAUSTED (rate limit)
#   503 -> UNAVAILABLE (modelo sobrecargado)
#   500 / 504 -> errores internos / timeouts del servicio
_TRANSIENT_STATUS_CODES = {429, 500, 503, 504}
_MAX_REINTENTOS = 2  # reintentos rápidos en el momento; si persiste, va a la cola
_BACKOFF_BASE = 2.0  # segundos: 2, 4, 8...


def _es_error_transitorio(error: Exception) -> bool:
    """
    True si conviene reintentar el error. Lo detectamos por el código
    HTTP que el SDK incluye en el mensaje, porque la jerarquía de
    excepciones de google-genai todavía cambia entre versiones.
    """
    texto = str(error)
    for code in _TRANSIENT_STATUS_CODES:
        if f"{code} " in texto or f"{code}:" in texto:
            return True
    # Algunos timeouts/conexiones rotas no traen código pero sí son
    # transitorios: los marcamos por nombre de excepción.
    nombre = type(error).__name__.lower()
    return any(k in nombre for k in ("timeout", "connection", "unavailable"))


def _stats_union() -> dict[str, str]:
    """
    Devuelve {stat_key: descripcion} con la UNIÓN de las stats de todos
    los juegos. Si dos juegos comparten una stat con descripciones
    distintas, se conserva la primera (debería ser igual de todos modos).
    """
    union: dict[str, str] = {}
    for cfg in GAMES.values():
        for stat_key, info in cfg["stats"].items():
            if stat_key in union:
                continue
            desc = info["desc"] if isinstance(info, dict) else info
            union[stat_key] = desc
    return union


def _construir_esquema_universal() -> type[BaseModel]:
    """
    Esquema único que cubre todas las stats posibles de cualquier juego.
    Si una captura concreta no tiene una stat (porque ese juego no la
    usa), Gemini la deja vacía y el bot la ignora.
    """
    campos: dict = {
        "stats_detected": (
            bool,
            Field(
                description=(
                    "True solo si la captura es legible y se ven con "
                    "claridad la tarjeta de estadísticas y el código de "
                    "isla. False si está borrosa, recortada, no es una "
                    "pantalla de estadísticas, o no aparece el código "
                    "de isla."
                )
            ),
        ),
        "player_name": (
            str,
            Field(description=NOMBRE_JUGADOR_DESC),
        ),
        "name_fully_visible": (
            bool,
            Field(
                description=(
                    "True si el nombre del jugador (texto blanco bajo "
                    "el avatar) se ve COMPLETO en la captura, sin "
                    "estar recortado por el borde de la imagen ni "
                    "tapado por otros elementos. False si la tarjeta "
                    "LIFETIME STATS está cortada por algún borde y el "
                    "nombre no se aprecia completo, o si solo se ve "
                    "una parte del texto (por ejemplo termina en '...' "
                    "o se corta a mitad de letra). En caso de duda, "
                    "devuelve False."
                )
            ),
        ),
        "island_code": (
            str,
            Field(description=ISLAND_CODE_DESC),
        ),
        "is_vip": (
            bool,
            Field(
                description=(
                    "True si el FONDO de la tarjeta de estadísticas es "
                    "AMARILLO (jugador VIP). False si el fondo es NEGRO "
                    "u OSCURO (jugador normal). Fíjate SOLO en el color "
                    "de fondo de la tarjeta, no en otros elementos."
                )
            ),
        ),
    }

    for stat_key, stat_desc in _stats_union().items():
        campos[stat_key] = (
            str,
            Field(
                description=(
                    f"{stat_desc}\n\n"
                    f"Devuelve el valor EXACTAMENTE como aparece en la "
                    f"captura, conservando el sufijo de magnitud del "
                    f"juego (K, M, B, T, Qa, Qi, Sx, Sp, Oc, No, Dc, "
                    f"Un, Du, Tr, Qt, Qn, Se, St, Og, Nn, Vg, UVg). "
                    f"Ejemplos válidos: '1.2K', '45.7M', '3.14Qa'. NO "
                    f"incluyas '$', '/s', comas ni espacios: solo "
                    f"número y, opcionalmente, sufijo. Si esta "
                    f"estadística no es visible en la captura, "
                    f"devuelve cadena vacía."
                )
            ),
        )

    return create_model("UniversalStats", **campos)


# Construimos el esquema una sola vez al importar el módulo.
_ESQUEMA = _construir_esquema_universal()


_PROMPT = (
    "Eres un sistema de visión artificial analizando una captura de "
    "pantalla de un juego de Fortnite Creative ('Brainrots').\n\n"
    "Tu objetivo es extraer los datos del jugador DESDE LA TARJETA "
    "negra titulada 'LIFETIME STATS' (la que tiene borde arcoíris y "
    "muestra el avatar del jugador a la izquierda). Necesitas: "
    "nombre, código de isla, si es VIP (fondo amarillo de la tarjeta) "
    "o no (fondo oscuro), y las estadísticas visibles dentro de la "
    "tarjeta.\n\n"
    "REGLA FUNDAMENTAL: SÓLO usa valores que estén DENTRO de la "
    "tarjeta LIFETIME STATS. IGNORA por completo otros números "
    "visibles en la pantalla, como los del HUD lateral del juego "
    "(esquina izquierda, con iconos de billetes, rayo, etc.) o los "
    "del leaderboard del fondo. Aunque sean parecidos, NO son los "
    "valores que buscamos.\n\n"
    "CÓMO LEER LOS NÚMEROS (sigue ESTE orden estrictamente):\n"
    "  1. Cada valor numérico de la tarjeta tiene DOS PARTES "
    "     separadas POR UN ESPACIO: primero los DÍGITOS (con sus "
    "     decimales) y después el SUFIJO de magnitud. Por ejemplo: "
    "     en '$28 Oc/s', '28' son los dígitos y 'Oc' es el sufijo. "
    "     En '$1.2 Sx', '1.2' son los dígitos y 'Sx' es el sufijo.\n"
    "  2. PRIMERO lee la parte numérica (todo lo que está ANTES del "
    "     espacio): dígitos y, si hay, separador decimal con más "
    "     dígitos. Ignora el símbolo '$' si lo lleva delante.\n"
    "  3. DESPUÉS, lo que viene tras el espacio y antes de '/s' (si "
    "     hay) es el SUFIJO de magnitud. Los sufijos posibles son, "
    "     en orden creciente: K, M, B, T, Qa, Qi, Sx, Sp, Oc, No, "
    "     Dc, Un, Du, Tr, Qt, Qn, Se, St, Og, Nn, Vg, UVg. Pueden "
    "     ser de 1 o 2 letras. NO son notación científica estándar; "
    "     son propios del juego, así que NO los descartes aunque te "
    "     parezcan raros: Oc, Sx, Sp, Dc, Un, Du, etc. son TODOS "
    "     válidos.\n"
    "  4. Devuelve la concatenación de dígitos + sufijo, SIN espacio "
    "     intermedio, SIN '$', SIN '/s'. Por ejemplo: '$28 Oc/s' lo "
    "     devuelves como '28Oc'.\n"
    "  Ejemplos de lectura CORRECTA:\n"
    "    '$28 Oc/s'      -> '28Oc'      (dígitos '28' + sufijo 'Oc')\n"
    "    '$1.2 Sx'       -> '1.2Sx'\n"
    "    '$117.5 Sx'     -> '117.5Sx'\n"
    "    '$43.30 Qa/s'   -> '43.30Qa'\n"
    "    '$5 No'         -> '5No'\n"
    "  Errores típicos a EVITAR:\n"
    "    '$28 Oc/s'  ->  '280'    (MAL: te has comido el sufijo 'Oc')\n"
    "    '$1.2 Sx'   ->  '12'     (MAL: te has comido el sufijo y el punto)\n"
    "    '$5 No'     ->  '5'      (MAL: te has comido el sufijo 'No')\n\n"
    "OTRAS REGLAS:\n"
    "- Sigue al pie de la letra las descripciones de cada campo del "
    "esquema JSON.\n"
    "- Si una estadística no es visible en la tarjeta, devuelve "
    "cadena vacía en ese campo. No inventes valores.\n"
    "- Si la imagen está borrosa, no se ve la tarjeta LIFETIME STATS, "
    "o no aparece el código de isla, pon stats_detected=false."
)


def _extraer_sync(image_bytes: bytes, mime_type: str) -> dict:
    """Llamada bloqueante a Gemini. Devuelve un dict ya validado."""
    response = _client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            _PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_ESQUEMA,
        ),
    )

    parsed = response.parsed
    if parsed is None:
        if not response.text:
            raise ValueError("Gemini no devolvió ninguna respuesta.")
        parsed = _ESQUEMA.model_validate_json(response.text)

    return parsed.model_dump()


class GeminiTransientError(Exception):
    """
    Error transitorio de Gemini (sobrecarga 503, rate limit 429, timeout)
    que persiste tras los reintentos rápidos. El bot lo trata encolando
    la captura para reintentarla en la siguiente ejecución, SIN avisar al
    usuario (no es culpa suya).
    """


async def extract_stats_from_image(
    image_bytes: bytes, mime_type: str
) -> dict:
    """
    Hace un par de reintentos RÁPIDOS para errores transitorios momentáneos.
    Si el error transitorio persiste, lanza GeminiTransientError para que
    el bot encole la captura y la reintente en la siguiente pasada.
    Los errores DEFINITIVOS (no transitorios) se propagan tal cual.
    """
    ultimo_error: Exception | None = None
    for intento in range(1, _MAX_REINTENTOS + 1):
        try:
            return await asyncio.to_thread(_extraer_sync, image_bytes, mime_type)
        except Exception as error:
            ultimo_error = error
            if not _es_error_transitorio(error):
                # Error definitivo (no lo arregla esperar): se propaga.
                raise
            if intento >= _MAX_REINTENTOS:
                break

            # Backoff exponencial corto con jitter: 2s, 4s ± 25%.
            espera = _BACKOFF_BASE ** intento
            espera += random.uniform(0, espera * 0.25)
            print(
                f"[RETRY] Gemini transitorio (intento {intento}/"
                f"{_MAX_REINTENTOS}), reintento rápido en {espera:.1f}s: {error}"
            )
            await asyncio.sleep(espera)

    # Agotados los reintentos rápidos y sigue siendo transitorio:
    # lo marcamos como GeminiTransientError para que el bot lo ENCOLE
    # en vez de avisar al usuario.
    raise GeminiTransientError(str(ultimo_error)) from ultimo_error
