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

from config import GEMINI_API_KEY, GEMINI_MODEL

# El cliente se crea una sola vez al importar el módulo.
_client = genai.Client(api_key=GEMINI_API_KEY)


class PlayerStats(BaseModel):
    """
    Si en el futuro añades más cosas a la base de datos (ej: nivel, clan...),
    solo tienes que añadir aquí la variable y Gemini la buscará automáticamente.
    """
    stats_detected: bool = Field(
        description="True si logras identificar el recuadro con borde de colores (arcoíris). False en caso contrario."
    )
    player_name: str = Field(
        description="El nombre del jugador (el texto blanco debajo del avatar)."
    )
    is_vip: bool = Field(
        default=False,
        description="True si el color de fondo del recuadro es AMARILLO. False si es negro u oscuro."
    )
    
    # --- AQUÍ ESTÁ LA MAGIA DINÁMICA ---
    cash: int = Field(
        description=(
            "Asigna a este campo el número de la estadística que más sentido tenga "
            "como 'Puntuación' o 'Dinero' (ejemplo: líneas amarillas o verdes como "
            "INCOME, CASH, MONEY, PUNTOS, etc.)."
        )
    )
    kills: int = Field(
        description=(
            "Asigna a este campo el número de la estadística que más sentido tenga "
            "como 'Bajas' o 'Aperturas' (ejemplo: líneas rojas o azules como "
            "PACKS OPENED, CARDS, KILLS, BAJAS, etc.)."
        )
    )

# Instrucción súper genérica y limpia
_PROMPT = (
    "Eres un sistema de visión artificial. Tu ÚNICO objetivo es localizar en la imagen "
    "un recuadro de estadísticas con un borde de múltiples colores (arcoíris).\n\n"
    "REGLA DE ORO: IGNORA POR COMPLETO el resto de la pantalla (fondo, chat, menús). "
    "Céntrate SOLO en el interior del recuadro.\n\n"
    "Usa tu lógica para extraer los datos de ese recuadro y rellenar las variables "
    "que te pido en el esquema JSON, basándote en las descripciones que te he dado "
    "para cada variable. Extrae solo los números enteros, sin letras ni símbolos."
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
