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

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, create_model

from config import GEMINI_API_KEY, GEMINI_MODEL
from games import GAMES, ISLAND_CODE_DESC, NOMBRE_JUGADOR_DESC

_client = genai.Client(api_key=GEMINI_API_KEY)


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
    "Tu objetivo es extraer del jugador principal: nombre, código de "
    "isla, si es VIP (fondo amarillo) o no (fondo oscuro), y las "
    "estadísticas visibles.\n\n"
    "REGLAS:\n"
    "- Sigue al pie de la letra las descripciones de cada campo del "
    "esquema JSON.\n"
    "- Para los valores numéricos: tal cual se ven, con su sufijo de "
    "magnitud (K, M, B, T, Qa, Qi, ..., UVg) y decimales. Sin '$', "
    "sin '/s', sin comas, sin espacios.\n"
    "- Si una estadística no es visible en esta captura, devuelve "
    "cadena vacía en ese campo. No inventes valores.\n"
    "- Si la imagen está borrosa, no es una pantalla de estadísticas, "
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


async def extract_stats_from_image(
    image_bytes: bytes, mime_type: str
) -> dict:
    """
    Versión asíncrona. Ya no recibe game_config: el esquema es universal
    y el juego se identifica DESPUÉS leyendo 'island_code' del resultado.
    """
    return await asyncio.to_thread(_extraer_sync, image_bytes, mime_type)
