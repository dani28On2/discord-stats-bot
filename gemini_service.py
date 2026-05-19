"""
gemini_service.py
=================
Habla con la API de Gemini.

La CLAVE de esta versión multi-juego: el esquema Pydantic que Gemini debe
rellenar se CONSTRUYE EN TIEMPO DE EJECUCIÓN a partir de la configuración
del juego (games.py). Así cada juego tiene sus propias stats sin tocar
este archivo.

Una llamada típica devuelve algo así (para Kick A Lucky Block):
    {
      "stats_detected": True,
      "player_name": "Pepe",
      "income": 1200,
      "cash": 45000
    }
"""

import asyncio

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, create_model

from config import GEMINI_API_KEY, GEMINI_MODEL

# Cliente único reutilizable.
_client = genai.Client(api_key=GEMINI_API_KEY)


def _construir_esquema(game_config: dict) -> type[BaseModel]:
    """
    Crea un modelo Pydantic A MEDIDA para este juego.

    Campos comunes a todos los juegos:
      - stats_detected (bool): si la captura es legible.
      - player_name   (str):   nombre del jugador.

    Campos dinámicos: uno por cada stat declarada en games.py.
    Todas las stats numéricas se modelan como int para simplificar.
    """
    campos: dict = {
        "stats_detected": (
            bool,
            Field(
                description=(
                    "True solo si la captura es legible y se pueden leer "
                    "con seguridad el nombre del jugador y TODAS las "
                    "estadísticas pedidas. False si está borrosa, "
                    "recortada o no parece una pantalla de estadísticas."
                )
            ),
        ),
        "player_name": (
            str,
            Field(description=game_config["player_name_description"]),
        ),
    }

    for stat_key, stat_desc in game_config["stats"].items():
        campos[stat_key] = (
            int,
            Field(
                description=(
                    f"{stat_desc} Devuelve SOLO el número entero, sin "
                    f"comas, sin puntos de miles, sin texto."
                )
            ),
        )

    # create_model construye una clase Pydantic en tiempo de ejecución.
    return create_model(f"Stats_{game_config['channel']}", **campos)


def _construir_prompt(game_config: dict) -> str:
    """Instrucción específica para este juego (más fiable que un prompt genérico)."""
    nombres_stats = ", ".join(game_config["stats"].keys())
    return (
        f"Eres un sistema de visión artificial analizando una captura de "
        f"pantalla del juego '{game_config['display_name']}'.\n\n"
        f"Tu objetivo es extraer del jugador principal los siguientes "
        f"datos: nombre y las estadísticas [{nombres_stats}].\n\n"
        f"REGLAS:\n"
        f"- Sigue al pie de la letra las descripciones de cada campo del "
        f"esquema JSON; ahí te indico qué color/posición tiene cada dato.\n"
        f"- Los números deben ser ENTEROS, sin comas ni símbolos. Si hay "
        f"sufijos como K, M, B, T conviértelos al entero real "
        f"(1.2K = 1200, 3M = 3000000).\n"
        f"- Si la imagen está borrosa, no es del juego correcto, o no "
        f"puedes leer algún dato con CERTEZA, pon stats_detected=false y "
        f"deja los números a 0. NO inventes datos."
    )


def _extraer_sync(image_bytes: bytes, mime_type: str, game_config: dict) -> dict:
    """Llamada bloqueante a Gemini. Devuelve un dict ya validado."""
    esquema = _construir_esquema(game_config)
    prompt = _construir_prompt(game_config)

    response = _client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=esquema,
        ),
    )

    parsed = response.parsed
    if parsed is None:
        if not response.text:
            raise ValueError("Gemini no devolvió ninguna respuesta.")
        parsed = esquema.model_validate_json(response.text)

    # Devolvemos un dict normal para que el resto del código no dependa
    # de la clase generada dinámicamente.
    return parsed.model_dump()


async def extract_stats_from_image(
    image_bytes: bytes, mime_type: str, game_config: dict
) -> dict:
    """Versión asíncrona. Devuelve un dict con las stats del juego."""
    return await asyncio.to_thread(
        _extraer_sync, image_bytes, mime_type, game_config
    )
