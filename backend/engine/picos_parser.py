"""Lectura de los datos de picos desde un informe guardado.

Un mismo campo `analisis.diagnostico` puede venir de dos épocas:

  * **legacy (taxonomía v1)** — `True peak: +0.5 dBTP (clipping)`. La palabra
    entre paréntesis usaba una definición que hoy sabemos incorrecta:
    "clipping" significaba simplemente `true_peak > 0`.
  * **v2** — `True peak: +0.5 dBTP` + `Sample peak: -0.8 dBFS` +
    `Categoría de picos: true_peak_over` + `Taxonomía de picos: v2`.

Regla, y es la que evita corromper las series históricas: **un informe legacy
NO se traduce a la taxonomía nueva**. El texto viejo no permite distinguir un
over de true peak de un archivo de coma flotante con overs recuperables, que
es exactamente lo que v2 separa. Traducirlo sería inventar el dato que falta.

Por eso `fuente` viaja siempre en el resultado: quien consuma esto tiene que
poder separar los dos mundos, no mezclarlos en una media.

Vive en `engine/` para que lo compartan el estudio histórico, el dashboard
(vía su propia copia en JS) y los tests, en vez de tener tres regex distintas.
"""

import re

TP_VALOR_RE = re.compile(r"True peak:\s*([-+]?[\d.]+)\s*dBTP")
TP_LEGACY_NIVEL_RE = re.compile(r"True peak:\s*[-+]?[\d.]+\s*dBTP\s*\((\w+)\)")
SP_VALOR_RE = re.compile(r"Sample peak:\s*([-+]?[\d.]+)\s*dBFS")
CAT_V2_RE = re.compile(r"Categor[íi]a de picos:\s*(\S+)")
TAXONOMIA_RE = re.compile(r"Taxonom[íi]a de picos:\s*v(\d+)")

# Equivalencia SOLO informativa, para poder explicar en un informe qué
# significaba la etiqueta antigua. No se usa para convertir datos.
SIGNIFICADO_LEGACY = {
    "clipping": "true peak > 0 dBTP (la v1 lo llamaba clipping sin comprobar muestras)",
    "streaming": "true peak entre -1 y 0 dBTP",
    "ok": "true peak <= -1 dBTP",
}


def leer_picos(informe: str) -> dict:
    """Extrae los datos de picos de un informe, diciendo de qué época son.

    Devuelve siempre las mismas claves:
        tp, sp, categoria, nivel_legacy, taxonomia, fuente

    `fuente` ∈ {"v2", "legacy", "legacy_sin_nivel", "ninguna"}.
    `categoria` solo tiene valor si `fuente == "v2"`.
    `nivel_legacy` solo tiene valor si `fuente == "legacy"`.
    """
    informe = informe or ""
    m_tp = TP_VALOR_RE.search(informe)
    m_sp = SP_VALOR_RE.search(informe)
    m_cat = CAT_V2_RE.search(informe)
    m_leg = TP_LEGACY_NIVEL_RE.search(informe)
    m_tax = TAXONOMIA_RE.search(informe)

    if m_cat:
        fuente = "v2"
    elif m_leg:
        fuente = "legacy"
    elif m_tp:
        # Hubo una ventana en la que se escribía el valor sin nivel.
        fuente = "legacy_sin_nivel"
    else:
        fuente = "ninguna"

    return {
        "tp": float(m_tp.group(1)) if m_tp else None,
        "sp": float(m_sp.group(1)) if m_sp else None,
        "categoria": m_cat.group(1) if fuente == "v2" else None,
        "nivel_legacy": m_leg.group(1) if fuente == "legacy" else None,
        "taxonomia": int(m_tax.group(1)) if m_tax else (2 if fuente == "v2" else 1),
        "fuente": fuente,
    }


def etiqueta_comparable(picos: dict) -> str:
    """Etiqueta que SÍ se puede comparar entre épocas.

    Se construye solo con el valor numérico del true peak, que significa lo
    mismo en las dos taxonomías. Sirve para series históricas que necesiten
    cruzar análisis viejos y nuevos sin mentir.

    Deliberadamente NO devuelve `overs_float_recuperables`: eso exige conocer
    el formato del archivo, dato que los análisis legacy no tienen.
    """
    tp = picos.get("tp")
    if tp is None:
        return "sin_dato"
    if tp > 0:
        return "tp_sobre_0"
    if tp > -1:
        return "tp_entre_m1_y_0"
    return "tp_bajo_m1"
