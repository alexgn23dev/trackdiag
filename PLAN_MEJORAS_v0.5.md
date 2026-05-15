# Plan de mejoras v0.5 — Post-lanzamiento

Basado en feedback real de 46 usuarios (13-15 mayo 2026).
Implementar en rama `dev`, probar en local, y mergear a `main` solo tras OK de Alex.

---

## 1. Recalibrar umbrales de exceso de graves (URGENTE)

**Problema:** muchos tracks marcados con exceso de graves que en realidad están bien para su género.

**Archivo:** `backend/engine/extractor.py` líneas 132-137

**Cambio:** subir umbrales genéricos de 18/24 a 20/26:

```python
if diff_grave_media > 26:
    balance_grave = "excesivo"
elif diff_grave_media > 20:
    balance_grave = "elevado"
else:
    balance_grave = "normal"
```

Combinado con el punto 4 (descuentos por género en reglas.py), los géneros con kick fuerte tendrán doble protección contra falsos positivos.

---

## 2. Consejos específicos cuando marca exceso de agudos/harshness

**Problema:** dice "revisar agudos" pero no dice si es el hi-hat, el synth, la voz, etc.

**Archivos:** `backend/engine/reglas.py` (líneas 330-366), `backend/engine/contextualizador.py`

**Plan:**
- En `reglas.py`, el diagnóstico `harshness_mezcla` ya detecta `zona_problema` ("presencia" 2-6kHz, "brillos" 6-10kHz, o "ambas"). Pero las razones son genéricas.
- Mejorar las razones cruzando `zona_problema` con el género:
  - `zona_problema == "presencia"` + género techno/minimal → "Probablemente hi-hats metálicos, claps o synth leads — revisa si algún elemento percusivo entre 2-6kHz está demasiado alto"
  - `zona_problema == "brillos"` + género trance/melodic → "Crashes, risers o reverbs de synths con demasiada cola en agudos — revisa los tails de tus efectos y reverbs"
  - `zona_problema == "ambas"` → "Todo el rango de agudos está elevado — posible falta de EQ correctivo general o compresión en el bus master que está empujando los agudos"
- En `contextualizador.py`, ampliar `_generar_tips_genero` para `harshness_mezcla` con consejos por género + zona (similar a lo que ya hace para `exceso_lowend` en líneas 301-314).

---

## 3. Consejos de LUFS/mastering accionables

**Problema:** ya mides LUFS y muestras el dato, pero la `referencia` es informativa, no accionable.

**Archivos:** `backend/engine/extractor.py` (líneas 366-401), `backend/engine/contextualizador.py`

**Plan:**
- En `_analizar_loudness`, añadir campo `consejo_master` con texto accionable por nivel:
  - `nivel == "muy_alto"` → "Baja el ceiling del limiter a -1dB y reduce el input gain hasta que el LUFS integrado baje a -7/-8. Si pierdes pegada, el problema está en la mezcla, no en el mastering."
  - `nivel == "alto"` → "Estás en zona de master agresivo. Para streaming, no tiene sentido subir más de -8 LUFS — Spotify lo va a bajar igualmente. Considera apuntar a -9/-10 LUFS para mantener rango dinámico."
  - `nivel == "bajo"` → "Si el track está terminado, un mastering básico lo sube: limiter con ceiling a -1dB, input gain hasta -8/-10 LUFS. Si suena distorsionado al subir, hay problemas de mezcla que resolver primero."
- Añadir tabla de referencia LUFS por género en el contextualizador:
```python
LUFS_GENERO = {
    "techno": {"target": -8, "rango": "-7 a -9"},
    "hard_techno": {"target": -7, "rango": "-6 a -8"},
    "trance": {"target": -9, "rango": "-8 a -10"},
    "deep_house": {"target": -10, "rango": "-9 a -11"},
    "house": {"target": -9, "rango": "-8 a -10"},
    "tech_house": {"target": -8, "rango": "-7 a -9"},
    "minimal": {"target": -9, "rango": "-8 a -10"},
    "progressive_house": {"target": -10, "rango": "-9 a -11"},
    "melodic_techno": {"target": -9, "rango": "-8 a -10"},
    "progressive_trance": {"target": -9, "rango": "-8 a -10"},
}
```

---

## 4. Ampliar géneros + "Otro" como campo libre

**Problema:** faltan géneros que la audiencia usa. Un usuario puso "deep house" cuando era "micro house" y el motor diagnosticó mal.

**Archivos:** `frontend/index.html`, `backend/engine/reglas.py`, `backend/engine/contextualizador.py`, `backend/main.py`, Apps Script

### 4a. Nuevos géneros en el formulario

Añadir al select de género en `index.html`: `afro_house`, `indie_dance`, `hard_techno`, `downtempo`, `breaks`, `drum_and_bass`, `dubstep`, `psytrance`. Cada uno con su label bonito.

En `reglas.py`:
- Ampliar `generos_graves_ok` (línea 127) con los nuevos géneros que toleran más graves: `hard_techno`, `drum_and_bass`, `dubstep`
- Ampliar `generos_graves_menos` (línea 128) con géneros que toleran menos: `downtempo`, `indie_dance`
- Ampliar `generos_brillantes` y `generos_oscuros` (líneas 219-220) según corresponda

En `contextualizador.py`:
- Añadir los nuevos géneros a `DURACIONES_GENERO`, `ESTRUCTURA_GENERO`, `_label_genero`

### 4b. "Otro" como campo de texto libre

**Frontend (`index.html`):**
- Cuando el usuario elige "Otro" en el select, mostrar un `<input type="text" placeholder="Escribe tu género (ej: afro house, UK garage...)">` debajo.
- Guardar en `contexto.genero` = `"otro"` y en campo nuevo `contexto.genero_custom` = texto del usuario.
- Enviar ambos campos en el FormData.

**Backend (`main.py`):**
- Recoger `genero_custom` del form y pasarlo en el contexto.
- Incluir `genero_custom` como campo separado en el payload a Sheets.
- El motor sigue recibiendo `genero = "otro"` para la lógica de reglas.

**Apps Script:**
- Añadir columna `genero_custom` en la hoja de análisis.

**Dashboard (`dashboard.html`):**
- En métricas de género, todos los `genero == "otro"` cuentan como categoría "Otros".
- Al hacer click en "Otros", mostrar lista de textos escritos por usuarios con conteo: "afro house (3), UK garage (2), breakbeat (1)".
- NO agrupar automáticamente por similaridad — Alex decidirá qué géneros añadir al formulario viendo la data.

---

## Orden de implementación

1. **Recalibrar graves** (punto 1) — 5 min, cambio de 2 líneas
2. **Harshness específico** (punto 2) — 30 min
3. **LUFS accionable** (punto 3) — 30 min
4. **Ampliar géneros + otro libre** (punto 4) — 1-2 horas (toca frontend, backend, contextualizador, dashboard, apps script)

## Notas para Claude Code

- Lee CLAUDE.md antes de empezar.
- Trabaja SIEMPRE en rama `dev` — nunca toques `main` directamente.
- Antes de mergear a main, muestra un resumen de cambios para que Alex dé OK.
- Los archivos `apps_script.js` / `docs/apps-script-*.js` son referencia — cambiarlos aquí NO actualiza producción. Avisar a Alex que tiene que pegar manualmente en script.google.com.
- El frontend es single-file React+Tailwind sin build step. Para cambios en `index.html`, usar Edit con suficiente contexto (el archivo es grande).
