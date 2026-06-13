"""
verificar_plantilla.py
=======================
Comprueba que la plantilla del widget (widget_templates/leaderboard_widget.t3d)
contiene todos los objetos que el bot necesita reemplazar.

Úsalo tras colocar la plantilla:

    python verificar_plantilla.py

Si dice "TODO CORRECTO", el bot podrá generar los .txt sin problema.
"""

import os
import re
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
PLANTILLA = os.path.join(DIR, "widget_templates", "leaderboard_widget.t3d")

OBJETOS_REQUERIDOS = (
    [f"Name{i}" for i in range(1, 11)]
    + [f"Value{i}" for i in range(1, 11)]
    + ["Tittle"]
)


def main() -> int:
    if not os.path.exists(PLANTILLA):
        print(f"❌ No existe la plantilla en: {PLANTILLA}")
        print("   Crea el archivo y pega el T3D completo del widget.")
        return 1

    with open(PLANTILLA, encoding="utf-8") as f:
        t3d = f.read()

    if len(t3d) < 5000:
        print(
            f"⚠️  La plantilla parece demasiado corta "
            f"({len(t3d)} bytes). ¿Pegaste el T3D completo?"
        )

    faltan = []
    for name in OBJETOS_REQUERIDOS:
        patron = re.compile(
            r'Begin Object\b[^\n]*\bName="' + re.escape(name) + r'"'
        )
        if not patron.search(t3d):
            faltan.append(name)

    encontrados = len(OBJETOS_REQUERIDOS) - len(faltan)
    print(f"Objetos encontrados: {encontrados}/{len(OBJETOS_REQUERIDOS)}")

    if faltan:
        print(f"❌ Faltan estos objetos: {faltan}")
        print(
            "   Revisa que la plantilla sea el T3D completo y que los "
            "nombres de los widgets en UEFN sean Name1..Name10, "
            "Value1..Value10 y Tittle."
        )
        return 1

    # Comprobar también que hay líneas Text= en esos bloques.
    n_text = len(re.findall(r'Text=INVTEXT\(', t3d))
    print(f"Líneas Text=INVTEXT encontradas: {n_text}")
    print("✅ TODO CORRECTO. El bot podrá generar los widgets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
