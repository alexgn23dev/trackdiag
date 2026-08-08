"""Reconstrucción band-limited exacta — SOLO PARA TESTS.

Es la referencia contra la que se mide todo lo demás. No es "otra
implementación más": es la definición.

Un archivo de audio es una señal continua muestreada. El teorema de muestreo
dice que esa señal continua es única: la suma de sincs centradas en cada
muestra. El "true peak" es el máximo de esa señal continua. Calcularlo no
requiere elegir un filtro ni un número de taps — se obtiene rellenando de
ceros el espectro, que es la interpolación sinc exacta escrita en el dominio
de la frecuencia.

Por qué hacía falta
-------------------
Hasta ahora se comparaba el medidor de producción contra otros medidores
(ffmpeg, el FIR de la norma, Youlean). Todos ellos son aproximaciones con
sus propios filtros, y cuando discrepan no hay forma de saber cuál acierta.
Medido con `respuesta_por_frecuencia()`, ninguno es plano:

    reconstructor      error a 10 kHz    error a 21 kHz
    exacta                  0,000            0,000
    FIR 12 taps (norma)    +0,120           -0,688
    soxr_hq 4x              0,000           -3,792

Esta referencia da 0,000 a cualquier frecuencia por construcción, y reproduce
el valor analítico del seno a fs/4 (ver `test_reconstruccion.py`).

Coste
-----
No sirve para producción tal cual: una FFT del archivo entero a 16x pide del
orden de gigabytes en una pista larga. Para eso está `pico_exacto_por_bloques`.

Extensión fuera del archivo
---------------------------
La FFT asume extensión PERIÓDICA: el final empalma con el principio. Un DAC
real asume silencio. Las dos versiones coinciden salvo cuando el máximo cae
en los primeros o últimos milisegundos, y ahí la diferencia es información,
no un fallo — por eso están las dos.
"""

import numpy as np

FACTOR_POR_DEFECTO = 16


def _interpolar(x: np.ndarray, factor: int) -> np.ndarray:
    """Interpolación sinc exacta por relleno de ceros en frecuencia."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n == 0:
        return np.zeros(0)
    X = np.fft.rfft(x)
    Y = np.zeros(n * factor // 2 + 1, dtype=complex)
    Y[:len(X)] = X
    # El bin de Nyquist es real y se reparte entre +f y -f al ampliar la
    # banda. Sin esto, una señal con energía justo en Nyquist se reconstruye
    # con el doble de amplitud de la que le toca.
    if n % 2 == 0:
        Y[n // 2] *= 0.5
    return np.fft.irfft(Y, n * factor) * factor


def reconstruir(x: np.ndarray, factor: int = FACTOR_POR_DEFECTO,
                borde: str = "periodico", guarda: int = 8192) -> np.ndarray:
    """Señal continua reconstruida, muestreada a `factor`x.

    borde="periodico"  el archivo se repite (lo que asume la FFT).
    borde="silencio"   fuera del archivo hay silencio (lo que hace un DAC).
    """
    x = np.asarray(x, dtype=np.float64)
    if borde == "periodico":
        return _interpolar(x, factor)
    if borde != "silencio":
        raise ValueError(f"borde desconocido: {borde}")
    xp = np.concatenate([np.zeros(guarda), x, np.zeros(guarda)])
    up = _interpolar(xp, factor)
    return up[guarda * factor: (guarda + len(x)) * factor]


def _db(v: float) -> float:
    return 20.0 * float(np.log10(v)) if v > 1e-12 else -99.0


def pico_exacto(data: np.ndarray, factor: int = FACTOR_POR_DEFECTO,
                borde: str = "periodico") -> float:
    """True peak exacto en dBTP de una señal (N,) o (N, canales)."""
    arr = np.asarray(data, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[:, None]
    pico = 0.0
    for ch in range(arr.shape[1]):
        up = reconstruir(arr[:, ch], factor, borde)
        if len(up):
            pico = max(pico, float(np.max(np.abs(up))))
    return _db(pico)


def pico_exacto_por_bloques(data: np.ndarray, factor: int = 8,
                            bloque: int = 1 << 16, solape: int = 1024) -> float:
    """El mismo valor, procesando por trozos con solape.

    Cada trozo se interpola entero y se descarta el solape, donde el empalme
    circular del bloque contamina. Sirve para pistas largas, donde la FFT
    completa no cabe en memoria.
    """
    arr = np.asarray(data, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr[:, None]
    paso = bloque - 2 * solape
    if paso <= 0:
        raise ValueError("el bloque tiene que ser mayor que el doble del solape")
    pico = 0.0
    for ch in range(arr.shape[1]):
        x = arr[:, ch]
        n = len(x)
        for i in range(0, n, paso):
            trozo = x[max(0, i - solape): i + paso + solape]
            if len(trozo) < 16:
                continue
            up = _interpolar(trozo, factor)
            a = solape * factor if i > 0 else 0
            b = len(up) - solape * factor if i + paso < n else len(up)
            pico = max(pico, float(np.max(np.abs(up[a:b]))))
    return _db(pico)


def respuesta_por_frecuencia(medidor, sr: int = 44100, n: int = 1 << 15,
                             frecuencias=None, n_fases: int = 13) -> list:
    """Caracteriza un medidor de picos: cuánto se desvía a cada frecuencia.

    Se le pasa un seno de amplitud 1,0 — cuyo pico real es 0 dB a CUALQUIER
    frecuencia — y se anota lo que devuelve. Lo que se aparte de 0 es error
    del reconstructor, no de la señal.

    `medidor` recibe (x, sr) y devuelve dBTP.

    Dos cuidados que hacen falta para que la medida signifique algo:
      * la frecuencia se ajusta a un bin exacto de la FFT, para que la
        extensión periódica del buffer no invente un salto;
      * se descarta 1/8 del buffer en cada extremo, para que no mande el
        transitorio de arranque de ningún filtro.
    """
    if frecuencias is None:
        frecuencias = [1000, 5000, 10000, 15000, 18000, 20000, 21000, 22000]
    salida = []
    for objetivo in frecuencias:
        k = round(objetivo * n / sr)
        f = k * sr / n
        peor = -99.0
        for fase in np.linspace(0.0, np.pi, n_fases):
            t = np.arange(n) / sr
            peor = max(peor, medidor(np.sin(2 * np.pi * f * t + fase), sr))
        salida.append({"objetivo_hz": objetivo, "hz": f,
                       "pct_nyquist": 100.0 * f / (sr / 2.0),
                       "error_db": round(peor, 4)})
    return salida


def recorte_util(arr: np.ndarray, fraccion: int = 8) -> np.ndarray:
    """Descarta los extremos de una señal sobremuestreada.

    Lo usan los medidores de `respuesta_por_frecuencia` para no medir el
    transitorio de arranque del filtro en vez de la señal.
    """
    m = len(arr) // fraccion
    return arr[m:-m] if m and len(arr) > 2 * m else arr
