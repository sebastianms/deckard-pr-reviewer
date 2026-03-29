---
description: Ejecuta una inspección completa de código estilo Officer K sobre todo el código fuente del repositorio, aplicando las reglas de Clean Code.
---

Ejecuta una inspección completa de código estilo Officer K (Blade Runner) sobre el repositorio actual.

## Pasos

1. Lee el archivo de reglas ubicado en `<DECKARD_PATH>/rules/rules.md`. Estas son las reglas que debes aplicar estrictamente. DECKARD_PATH es el directorio raíz del proyecto actual.

2. Obtén la lista completa de archivos rastreados por git:
   ```bash
   git ls-files
   ```

3. Ignora los siguientes archivos del análisis:
   - Archivos `.lock`, `package.json`, `package-lock.json`, `.gitignore`
   - Archivos de test (que contengan `/tests/`, `.test.` o `_test.` en su ruta)
   - Archivos de assets o binarios (`.png`, `.jpg`, `.svg`, `.ico`, `.woff`, etc.)
   - Archivos de documentación (`.md`)

4. Si existe una carpeta `.logs/` en la raíz del proyecto, lee su contenido como contexto adicional de arquitectura y decisiones técnicas.

5. Lee cada archivo relevante en su totalidad y analiza TODO el código — no solo los cambios recientes.

6. Identifica TODAS las violaciones de las reglas cargadas en el paso 1. Para cada violación, asigna una criticidad del 1 al 10.

7. Presenta los resultados en el siguiente formato:

   ### Si hay violaciones (criticidad >= 8):
   ```
   🔍 INSPECCIÓN COMPLETA DEL REPOSITORIO

   📄 Archivo: <ruta>
     ❌ [Rule ID] Violación: <descripción>
        Línea: <código de la línea>
        Sugerencia: <fix propuesto>
        Criticidad: [X/10]
   ```

   ### Si no hay violaciones:
   ```
   ✅ Inspección completa finalizada. Todo el código es humano. Misión cumplida, K.
   ```

8. Incluye al final un resumen: archivos inspeccionados, total de violaciones, y acciones concretas a tomar ordenadas por criticidad.

> **IMPORTANTE:** No sugieras instalar nuevas dependencias. Enfócate exclusivamente en calidad de código según las reglas.
