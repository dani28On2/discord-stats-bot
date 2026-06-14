"""
widget_export.py
================
Convierte un leaderboard (lista de filas {name, value, isVip}) en el
TEXTO T3D de un widget de UEFN, listo para pegar con Ctrl+V en el
Designer del WBP_LeaderboardData.

Cómo funciona
-------------
Partimos de una PLANTILLA T3D (el texto que se copia desde UEFN al
seleccionar el widget y pulsar Ctrl+C). En esa plantilla, cada celda de
texto es un objeto con un nombre único:

    Begin Object Class=...UEFN_TextBlock_C Name="Name1" ...
       Text=INVTEXT("loquesea")
       ...
    End Object

Reemplazamos SOLO la línea `Text=INVTEXT("...")` dentro de los bloques:
    - Name1 .. Name10   -> nombre del jugador (o "" si no hay tantos)
    - Value1 .. Value10 -> valor formateado (o "" si no hay tantos)
    - Tittle            -> título de la stat (ej. "MOST CASH")

Además, el color del título y de los valores se ajusta al color de la
stat (en las líneas ColorAndOpacity=(SpecifiedColor=(...))).

El reemplazo se hace bloque a bloque (localizando cada `Name="..."`),
no con un regex global, para no tocar celdas equivocadas.
"""

import re

# Nº de filas que tiene la plantilla del widget.
WIDGET_ROWS = 10


def _escape_t3d_text(texto: str) -> str:
    """
    Escapa un texto para meterlo dentro de INVTEXT("...").
    En T3D las comillas dobles se escapan con backslash. Mantenemos los
    caracteres Unicode tal cual (UEFN los acepta: ya vimos nombres en
    japonés en la plantilla original).
    """
    if texto is None:
        return ""
    return str(texto).replace("\\", "\\\\").replace('"', '\\"')


def _reemplazar_text_en_bloque(t3d: str, object_name: str, nuevo_texto: str) -> str:
    """
    Dentro del bloque `Begin Object ... Name="<object_name>" ... End Object`,
    reemplaza la primera línea `Text=INVTEXT("...")` por el nuevo texto.

    Si el bloque no se encuentra, devuelve el t3d intacto (y es
    responsabilidad del llamante avisar).
    """
    # Localizamos el inicio del bloque por su Name="..." exacto.
    # El patrón ancla en 'Begin Object' + cualquier cosa + Name="<nombre>"
    patron_inicio = re.compile(
        r'Begin Object\b[^\n]*\bName="' + re.escape(object_name) + r'"'
    )
    m = patron_inicio.search(t3d)
    if not m:
        return t3d  # bloque no encontrado

    inicio = m.start()
    # El final del bloque es el primer 'End Object' tras el inicio.
    fin_match = re.search(r'\n\s*End Object', t3d[inicio:])
    if not fin_match:
        return t3d
    fin = inicio + fin_match.end()

    bloque = t3d[inicio:fin]

    # Reemplazar la primera ocurrencia de Text=INVTEXT("...") o
    # Text=NSLOCTEXT(...) dentro de ESE bloque.
    nuevo_valor = f'Text=INVTEXT("{_escape_t3d_text(nuevo_texto)}")'
    bloque_nuevo, n = re.subn(
        r'Text=(?:INVTEXT|NSLOCTEXT)\([^\n]*\)',
        nuevo_valor,
        bloque,
        count=1,
    )
    if n == 0:
        # El bloque no tenía línea Text=...; no lo tocamos.
        return t3d

    return t3d[:inicio] + bloque_nuevo + t3d[fin:]


def _color_a_specified(color_rgb: tuple[float, float, float]) -> str:
    """Convierte (r,g,b) 0-1 en la cadena SpecifiedColor de UEFN."""
    r, g, b = color_rgb
    return (
        f"ColorAndOpacity=(SpecifiedColor="
        f"(R={r:.6f},G={g:.6f},B={b:.6f},A=1.000000))"
    )


def _oscurecer(color_rgb: tuple[float, float, float], factor: float = 0.24) -> tuple[float, float, float]:
    """
    Devuelve una versión oscura del color (para el borde del título).
    El factor 0.24 se derivó del verde de referencia que el juego usa
    (stat G=0.882 -> outline G=0.214). No es exacto para todos los
    colores, pero da un borde oscuro consistente.
    """
    return tuple(c * factor for c in color_rgb)


def _reemplazar_color_en_bloque(
    t3d: str, object_name: str, color_rgb: tuple[float, float, float]
) -> str:
    """
    Reemplaza la línea ColorAndOpacity=(SpecifiedColor=(...)) dentro del
    bloque indicado. Si el bloque no tiene esa línea, no hace nada (no
    todos los textos llevan color explícito).
    """
    patron_inicio = re.compile(
        r'Begin Object\b[^\n]*\bName="' + re.escape(object_name) + r'"'
    )
    m = patron_inicio.search(t3d)
    if not m:
        return t3d
    inicio = m.start()
    fin_match = re.search(r'\n\s*End Object', t3d[inicio:])
    if not fin_match:
        return t3d
    fin = inicio + fin_match.end()

    bloque = t3d[inicio:fin]
    nuevo_color = _color_a_specified(color_rgb)
    # SpecifiedColor puede tener paréntesis anidados; capturamos hasta el
    # cierre del ColorAndOpacity. Usamos un patrón que abarca el grupo
    # completo (R=...,G=...,B=...,A=...).
    bloque_nuevo, n = re.subn(
        r'ColorAndOpacity=\(SpecifiedColor=\(R=[^)]*\)\)',
        nuevo_color,
        bloque,
        count=1,
    )
    if n == 0:
        return t3d  # no tenía color explícito; lo dejamos
    return t3d[:inicio] + bloque_nuevo + t3d[fin:]


def _reemplazar_outline_color_en_bloque(
    t3d: str, object_name: str, color_rgb: tuple[float, float, float]
) -> str:
    """
    Reemplaza el OutlineColor=(...) que está dentro del Font del bloque
    indicado (el borde del texto). Se usa para el título: borde en una
    versión oscura del color de la stat.
    """
    patron_inicio = re.compile(
        r'Begin Object\b[^\n]*\bName="' + re.escape(object_name) + r'"'
    )
    m = patron_inicio.search(t3d)
    if not m:
        return t3d
    inicio = m.start()
    fin_match = re.search(r'\n\s*End Object', t3d[inicio:])
    if not fin_match:
        return t3d
    fin = inicio + fin_match.end()

    bloque = t3d[inicio:fin]
    r, g, b = color_rgb
    nuevo = f"OutlineColor=(R={r:.6f},G={g:.6f},B={b:.6f},A=1.000000)"
    bloque_nuevo, n = re.subn(
        r'OutlineColor=\(R=[^)]*\)',
        nuevo,
        bloque,
        count=1,
    )
    if n == 0:
        return t3d
    return t3d[:inicio] + bloque_nuevo + t3d[fin:]


def build_widget_t3d(
    template_t3d: str,
    rows: list[dict],
    title: str | None = None,
    color_rgb: tuple[float, float, float] | None = None,
    rows_count: int = WIDGET_ROWS,
    template_project: str | None = None,
    target_project: str | None = None,
) -> str:
    """
    Devuelve el T3D con los datos del leaderboard sustituidos.

    Parámetros:
      template_t3d : la plantilla copiada desde UEFN.
      rows         : lista de filas [{name, value, isVip}, ...].
      title        : texto del título (ej. "MOST CASH"). Si None, no se
                     toca el título de la plantilla.
      color_rgb    : (r,g,b) 0-1 para el título y los valores. Si None,
                     no se tocan los colores.
      rows_count   : nº de filas del widget (por defecto 10).
      template_project : nombre del proyecto UEFN de la plantilla (ej.
                     "MT_LasersForBrainrots"). Es el MT_XXX que aparece
                     en las rutas de la plantilla.
      target_project : nombre del proyecto UEFN del juego destino (ej.
                     "MT_KeyboardMusicParkour"). Si ambos están dados y
                     son distintos, se reemplaza el proyecto en todas las
                     rutas para que el widget pegue bien en ese proyecto.
    """
    out = template_t3d

    # 0) Reescribir el proyecto en las rutas (ExportPath, etc.), si el
    #    juego destino vive en otro proyecto UEFN distinto al de la
    #    plantilla. Solo cambia el token MT_XXX; el resto de la ruta es
    #    idéntico entre proyectos.
    if template_project and target_project and template_project != target_project:
        out = out.replace(template_project, target_project)

    # 1) Nombres y valores, fila por fila.
    for i in range(1, rows_count + 1):
        if i <= len(rows):
            fila = rows[i - 1]
            nombre = str(fila.get("name", ""))
            valor = str(fila.get("value", ""))
        else:
            # Menos jugadores que filas: vaciar las sobrantes.
            nombre = ""
            valor = ""
        out = _reemplazar_text_en_bloque(out, f"Name{i}", nombre)
        out = _reemplazar_text_en_bloque(out, f"Value{i}", valor)

    # 2) Título de la stat (el objeto se llama "Tittle" en la plantilla).
    if title is not None:
        out = _reemplazar_text_en_bloque(out, "Tittle", title)

    # 3) Color del título y de todos los valores.
    if color_rgb is not None:
        # Título: color principal = color de la stat; borde (OutlineColor)
        # = versión oscura del mismo.
        out = _reemplazar_color_en_bloque(out, "Tittle", color_rgb)
        out = _reemplazar_outline_color_en_bloque(
            out, "Tittle", _oscurecer(color_rgb)
        )
        # Valores: color principal = color de la stat.
        for i in range(1, rows_count + 1):
            out = _reemplazar_color_en_bloque(out, f"Value{i}", color_rgb)

    return out


def hex_to_rgb01(color_hex: int) -> tuple[float, float, float]:
    """
    Convierte un color 0xRRGGBB (entero) en (r,g,b) normalizado 0-1,
    como espera UEFN. Nota: UEFN usa color LINEAL, pero la plantilla
    original guarda valores que ya casan con lo que se ve en el editor,
    así que pasamos el sRGB directo normalizado (es lo que hacía el
    pipeline previo y daba el color correcto en pantalla).
    """
    r = ((color_hex >> 16) & 0xFF) / 255.0
    g = ((color_hex >> 8) & 0xFF) / 255.0
    b = (color_hex & 0xFF) / 255.0
    return (r, g, b)
