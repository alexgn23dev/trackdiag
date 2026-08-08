"""Interpolador FIR 4× de ITU-R BS.1770-5, Anexo 2 — SOLO PARA TESTS.

Implementación de referencia del medidor de true-peak que describe la norma:
un banco polifásico de 4 fases × 12 coeficientes (48 taps) que reconstruye la
señal a 4× y toma el máximo absoluto.

NO sustituye al algoritmo de producción (`soxr_hq_8x` en engine/extractor.py).
Existe para poder comparar contra algo que sigue la letra de la norma en vez
de contra otra aproximación.

Diferencias respecto a la norma, declaradas:

* La norma atenúa 12,04 dB (×0,25) antes de filtrar para no desbordar en
  punto fijo, y compensa después. Aquí se trabaja en coma flotante de 64
  bits, así que la atenuación es una identidad matemática y se omite.
* La norma incluye un paso-bajo posterior opcional para sistemas que
  sobremuestrean más de 4×. No aplica a 4×.
* Los coeficientes están transcritos de la Tabla 3 del Anexo 2. Para que un
  error de transcripción no pase inadvertido, `verificar_coeficientes()`
  comprueba las propiedades estructurales que el banco debe cumplir
  (simetría entre fases y ganancia en continua), y los tests la ejecutan.

Comportamiento en los bordes: la norma no dice qué hay fuera del archivo.
Aquí se hace explícito con el parámetro `modo_borde`:

* "cero"    — se asume silencio fuera (lo que hace un DAC real al reproducir
              el archivo). Produce el transitorio de asentamiento del filtro.
* "extender"— se repite la primera y la última muestra. Aproxima el régimen
              estable y sirve para medir la señal sin el artefacto de borde.
"""

import numpy as np

# Tabla 3, Anexo 2 de ITU-R BS.1770 — 4 fases de 12 coeficientes.
COEFICIENTES_FASES = np.array([
    [0.0017089843750, 0.0109863281250, -0.0196533203125, 0.0332031250000,
     -0.0594482421875, 0.1373291015625, 0.9721679687500, -0.1022949218750,
     0.0476074218750, -0.0266113281250, 0.0148925781250, -0.0083007812500],
    [-0.0291748046875, 0.0292968750000, -0.0517578125000, 0.0891113281250,
     -0.1665039062500, 0.4650878906250, 0.7797851562500, -0.2003173828125,
     0.1015625000000, -0.0582275390625, 0.0330810546875, -0.0189208984375],
    [-0.0189208984375, 0.0330810546875, -0.0582275390625, 0.1015625000000,
     -0.2003173828125, 0.7797851562500, 0.4650878906250, -0.1665039062500,
     0.0891113281250, -0.0517578125000, 0.0292968750000, -0.0291748046875],
    [-0.0083007812500, 0.0148925781250, -0.0266113281250, 0.0476074218750,
     -0.1022949218750, 0.9721679687500, 0.1373291015625, -0.0594482421875,
     0.0332031250000, -0.0196533203125, 0.0109863281250, 0.0017089843750],
], dtype=np.float64)

OVERSAMPLING = 4
TAPS_POR_FASE = COEFICIENTES_FASES.shape[1]
# Retardo de grupo del banco, en muestras de entrada. Con 12 taps por fase el
# centro está en el tap 6; es la zona que hay que descartar a cada lado para
# quedarse con el régimen estable.
ASENTAMIENTO_MUESTRAS = TAPS_POR_FASE


def verificar_coeficientes(tol_simetria: float = 1e-12,
                           dc_min: float = 0.95, dc_max: float = 1.05) -> dict:
    """Comprueba las propiedades estructurales del banco polifásico.

    Un banco de interpolación bien transcrito cumple:
      1. La fase 3 es la fase 0 invertida y la fase 2 es la fase 1 invertida
         (el filtro prototipo es simétrico: fase lineal).
      2. Cada fase tiene ganancia en continua próxima a 1, para que una
         señal constante se reconstruya como esa misma constante.

    Devuelve el detalle; los tests comprueban el resultado.
    """
    c = COEFICIENTES_FASES
    simetria_03 = float(np.max(np.abs(c[3] - c[0][::-1])))
    simetria_12 = float(np.max(np.abs(c[2] - c[1][::-1])))
    ganancias_dc = [float(np.sum(fase)) for fase in c]
    return {
        "simetria_fase0_fase3": simetria_03,
        "simetria_fase1_fase2": simetria_12,
        "ganancias_dc": [round(g, 6) for g in ganancias_dc],
        "ganancia_dc_max_db": round(20 * np.log10(max(ganancias_dc)), 4),
        "ganancia_dc_min_db": round(20 * np.log10(min(ganancias_dc)), 4),
        "simetria_ok": simetria_03 <= tol_simetria and simetria_12 <= tol_simetria,
        "dc_ok": all(dc_min <= g <= dc_max for g in ganancias_dc),
    }


def _sobremuestrear_canal(x: np.ndarray, modo_borde: str) -> np.ndarray:
    """Devuelve la señal reconstruida a 4×, alineada con la entrada.

    La salida tiene 4 muestras por cada muestra de entrada; la muestra k·4+f
    corresponde a la fase f evaluada en la posición k.
    """
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n == 0:
        return np.zeros(0)

    pad = TAPS_POR_FASE
    if modo_borde == "extender":
        izq = np.full(pad, x[0])
        der = np.full(pad, x[-1])
    elif modo_borde == "cero":
        izq = np.zeros(pad)
        der = np.zeros(pad)
    else:
        raise ValueError(f"modo_borde desconocido: {modo_borde}")
    xp = np.concatenate([izq, x, der])

    salida = np.empty(len(xp) * OVERSAMPLING - (TAPS_POR_FASE - 1) * OVERSAMPLING)
    trozos = []
    for f in range(OVERSAMPLING):
        # 'valid' descarta las posiciones donde el filtro no está lleno.
        trozos.append(np.convolve(xp, COEFICIENTES_FASES[f], mode="valid"))
    largo = min(len(t) for t in trozos)
    salida = np.empty(largo * OVERSAMPLING)
    for f in range(OVERSAMPLING):
        salida[f::OVERSAMPLING] = trozos[f][:largo]
    return salida


def true_peak_dbtp(data: np.ndarray, modo_borde: str = "cero",
                   descartar_asentamiento: bool = False) -> float:
    """True peak en dBTP de una señal (N,) o (N, canales).

    `descartar_asentamiento=True` ignora la zona de los bordes en la que el
    filtro aún no está en régimen estable. Sirve para separar "lo que mide el
    filtro" de "lo que hace el filtro al arrancar".
    """
    picos = por_canal(data, modo_borde, descartar_asentamiento)
    if not picos:
        return -99.0
    pico = max(picos)
    return 20.0 * float(np.log10(pico)) if pico > 1e-12 else -99.0


def por_canal(data: np.ndarray, modo_borde: str = "cero",
              descartar_asentamiento: bool = False) -> list:
    """Máximo absoluto reconstruido de cada canal, en lineal."""
    arr = np.asarray(data, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[:, None]
    picos = []
    for ch in range(arr.shape[1]):
        up = _sobremuestrear_canal(arr[:, ch], modo_borde)
        if descartar_asentamiento:
            recorte = ASENTAMIENTO_MUESTRAS * OVERSAMPLING
            if len(up) > 2 * recorte:
                up = up[recorte:-recorte]
        picos.append(float(np.max(np.abs(up))) if len(up) else 0.0)
    return picos


def true_peak_desde_archivo(ruta: str, modo_borde: str = "cero",
                            descartar_asentamiento: bool = False) -> float:
    import soundfile as sf
    data, _sr = sf.read(ruta, always_2d=True, dtype="float64")
    return true_peak_dbtp(data, modo_borde, descartar_asentamiento)
