---
description: Ejecuta una revisión de código Deckard (Voight-Kampff) sobre los archivos modificados en el staging area, aplicando las reglas de Clean Code.
---

Ejecuta una revisión de código estilo Deckard (Voight-Kampff) sobre los cambios actuales.

## Pasos

1. Lee el archivo de reglas ubicado en `<DECKARD_PATH>/rules/rules.md`. Estas son las reglas que debes aplicar estrictamente.

2. Obtén el diff de los archivos en el staging area ejecutando:
   ```bash
   git diff --cached
   ```
   Si no hay archivos staged, usa `git diff` para revisar los cambios no staged.

3. Ignora los siguientes archivos del análisis:
   - Archivos `.lock`, `package.json`, `package-lock.json`, `.gitignore`
   - Archivos de test (que contengan `/tests/` o `.test.` en su ruta)

4. Si existe una carpeta `.logs/` en la raíz del proyecto, lee su contenido como contexto adicional de arquitectura y decisiones técnicas.

5. Para cada archivo modificado, analiza SOLAMENTE las líneas que comienzan con `+` (líneas añadidas). Las demás líneas son solo contexto.

6. Identifica TODAS las violaciones de las reglas cargadas en el paso 1. Para cada violación, asigna una criticidad del 1 al 10.

7. Presenta los resultados en el siguiente formato:

   ### Si hay violaciones (criticidad >= 8):
   ```
   🚨 ANOMALÍAS DETECTADAS

   📄 Archivo: <ruta>
     ❌ [Rule ID] Violación: <descripción>
        Línea: <código de la línea>
        Sugerencia: <fix propuesto>
        Criticidad: [X/10]
   ```

   ### Si no hay violaciones:
   ```
   ✅ Prueba Voight-Kampff superada. El código está limpio.
   ```

8. Si encontraste violaciones de criticidad 8 o superior, lista un resumen final con las acciones concretas que el desarrollador debe tomar antes de commitear.

> **IMPORTANTE:** No sugieras instalar nuevas dependencias. Enfócate exclusivamente en calidad de código según las reglas.
