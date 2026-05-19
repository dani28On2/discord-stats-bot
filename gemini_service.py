"""
gemini_service.py
=================
Responsable de hablar con la API de Gemini.

Recibe los bytes de una imagen (la captura de pantalla) y devuelve un
objeto Pydantic VALIDADO con el nombre del jugador, la puntuación y las
bajas. Usamos Structured Output: le pasamos un esquema Pydantic a Gemini
y el modelo está OBLIGADO a responder un JSON que cumpla ese esquema.
"""

import asyncio

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from src.config import GEMINI_API_KEY, GEMINI_MODEL

# El cliente se crea una sola vez al importar el módulo.
_client = genai.Client(api_key=GEMINI_API_KEY)


class PlayerStats(BaseModel):
    """
    Esquema que Gemini DEBE rellenar. Las descripciones (Field) se envían
    al modelo como pistas, así que cuanto más claras, mejor extracción.
    """

    stats_detected: bool = Field(
        description=(
            "True solo si la captura es legible y se pueden leer con "
            "seguridad el nombre, la puntuación y las bajas. "
            "False si la imagen está borrosa, recortada o no es una "
            "pantalla de estadísticas de partida."
        )
    )
    player_name: str = Field(
        description="Nombre o nick del jugador tal y como aparece en la captura."
    )
    score: int = Field(
        description="Puntuación TOTAL obtenida en la partida (solo el número entero)."
    )
    kills: int = Field(
        description="Número de bajas / kills del jugador (solo el número entero)."
    )


# Instrucción que acompaña a la imagen. Es explícita para reducir errores.
_PROMPT = (
    "Eres un analista de estadísticas de videojuegos. Observa esta captura "
    "de pantalla de una pantalla de resultados de partida y extrae los datos "
    "del jugador principal.\n"
    "- Devuelve la puntuación y las bajas como números enteros, sin comas ni "
    "puntos de miles ni texto.\n"
    "- Si la imagen está borrosa, no es una pantalla de estadísticas, o no "
    "puedes leer algún dato con certeza, pon stats_detected=false y usa 0 en "
    "los campos numéricos. No inventes datos."
)


def _extraer_sync(image_bytes: bytes, mime_type: str) -> PlayerStats:
    """
    Llamada SÍNCRONA y bloqueante a Gemini.
    No se llama directamente: se invoca a través de extract_stats_from_image,
    que la ejecuta en un hilo aparte para no congelar el bot.
    """
    response = _client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            # 1) La imagen en bytes
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            # 2) La instrucción de texto
            _PROMPT,
        ],
        config=types.GenerateContentConfig(
            # Forzamos respuesta JSON conforme al esquema Pydantic.
            response_mime_type="application/json",
            response_schema=PlayerStats,
        ),
    )

    # Con response_schema, el SDK ya valida y rellena `response.parsed`.
    stats = response.parsed
    if stats is None:
        # Plan B: parsear manualmente el texto JSON devuelto.
        if not response.text:
            raise ValueError("Gemini no devolvió ninguna respuesta.")
        stats = PlayerStats.model_validate_json(response.text)

    return stats


async def extract_stats_from_image(image_bytes: bytes, mime_type: str) -> PlayerStats:
    """
    Versión ASÍNCRONA pensada para usarse dentro de discord.py.

    La llamada a Gemini es bloqueante; si la ejecutáramos directamente,
    el bot dejaría de responder a todo lo demás mientras espera. Por eso
    la mandamos a un hilo con asyncio.to_thread.
    """
    return await asyncio.to_thread(_extraer_sync, image_bytes, mime_type)
