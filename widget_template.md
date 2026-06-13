# Plantilla del widget de UEFN

El bot genera los archivos `.txt` (T3D para pegar en UEFN) a partir de
**una plantilla** que tienes que colocar aquí.

## Qué archivo crear

Crea un archivo llamado **exactamente**:

```
widget_templates/leaderboard_widget.t3d
```

## Qué contenido debe tener

El **texto T3D completo** del widget `WBP_LeaderboardData`, es decir, lo
que se copia al portapapeles cuando en UEFN:

1. Abres el `WBP_LeaderboardData` en el Designer.
2. Seleccionas el nodo raíz del WidgetTree (el `CanvasPanel` de arriba).
3. Pulsas **Ctrl+C**.
4. Pegas aquí (en este archivo) con **Ctrl+V**.

Es el mismo texto que ya me pasaste una vez (empieza por
`Begin Object Class=/Script/UMG.CanvasPanel Name="CanvasPanel_28"` y
termina con el bloque del `Image_103` del icono de Discord).

## Importante

- El bot busca dentro de ese texto los objetos llamados `Name1`..`Name10`,
  `Value1`..`Value10` y `Tittle`, y reemplaza solo su línea de texto y
  (para Tittle y los Value) su color. **No cambies esos nombres** en el
  widget de UEFN, o el bot no los encontrará.
- Si algún día rehaces el widget desde cero y los nombres cambian, vuelve
  a exportar el T3D y reemplaza este archivo.
- El archivo debe estar en **UTF-8** (para que los nombres con caracteres
  japoneses, etc. se conserven). Cualquier editor moderno lo guarda así
  por defecto.

## Una sola plantilla para todos los juegos

La estructura del widget es la misma en los cuatro juegos: solo cambian
el título, el color y los datos, que el bot ya inyecta automáticamente
según la stat. Por eso basta con UNA plantilla aquí.

Si en el futuro un juego tuviera un widget con estructura distinta (por
ejemplo, distinto número de filas), habría que ampliar el código para
soportar varias plantillas. De momento no hace falta.
