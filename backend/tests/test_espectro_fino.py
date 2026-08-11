"""El espectro en tercios de octava que alimenta el gráfico.

Se mide aparte del mel por dos motivos, y los dos se comprueban aquí:

  1. **Ancho de banda honesto.** El análisis general carga a 22 050 Hz, así que
     por encima de 11 kHz no hay nada. El gráfico llegaba a 20 kHz alimentado
     desde ahí: la mitad derecha era una interpolación entre dos puntos, no una
     medida. Ahora se lee el archivo a su frecuencia real y lo que no existe se
     devuelve como None.

  2. **Resolución.** Seis bandas no son un espectro. El tercio de octava es lo
     que define IEC 61260 y lo que usa cualquier analizador.

La parte importante de este fichero es `TestContraLaTeoria`: no comprueba que
el código haga lo que escribí, comprueba que el resultado coincide con lo que
la física dice que tiene que salir. Un ruido blanco TIENE que subir 1 dB por
banda; si no sube, la medida está mal por mucho que el test de forma pase.
"""

import os
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.extractor import (  # noqa: E402
    _CENTROS_TERCIO,
    _espectro_tercios_octava,
)

SR = 44100


def sin_ponderar(f):
    return np.zeros_like(np.asarray(f, dtype=float))


def ponderacion_a(f):
    """La misma fórmula que usa el extractor (IEC 61672-1)."""
    f = np.asarray(f, dtype=float)
    f2 = f ** 2
    num = (12194.0 ** 2) * (f2 ** 2)
    den = ((f2 + 20.6 ** 2) * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2))
           * (f2 + 12194.0 ** 2))
    with np.errstate(divide="ignore", invalid="ignore"):
        ra = np.where(den > 0, num / den, 0.0)
        return np.where(ra > 0, 20 * np.log10(np.maximum(ra, 1e-30)) + 2.0, -80.0)


class Base(unittest.TestCase):
    def setUp(self):
        self.temporales = []

    def tearDown(self):
        for p in self.temporales:
            try:
                os.unlink(p)
            except OSError:
                pass

    def escribir(self, x, sr=SR):
        ruta = tempfile.mktemp(suffix=".wav")
        self.temporales.append(ruta)
        pico = float(np.max(np.abs(x))) or 1.0
        sf.write(ruta, (x / pico * 0.5).astype("float32"), sr)
        return ruta

    def niveles(self, ruta, dur=12, pond=sin_ponderar, clave="db"):
        r = _espectro_tercios_octava(ruta, 0, dur, pond)
        self.assertTrue(r, "el medidor se rindió y no debería")
        return r, [b[clave] for b in r["bandas"] if b[clave] is not None]


class TestContraLaTeoria(Base):
    """Señales cuyo espectro en tercios de octava se conoce de antemano."""

    def pendiente(self, db, desde_hz=100):
        """dB por banda, ajustada solo donde la FFT tiene bins de sobra."""
        i = _CENTROS_TERCIO.index(desde_hz)
        return float(np.polyfit(np.arange(len(db) - i), db[i:], 1)[0])

    def test_ruido_blanco_sube_1_db_por_banda(self):
        """Cada tercio de octava es 2^(1/3) más ancho que el anterior, así que
        recoge 10·log10(2^(1/3)) = 1.0 dB más de un ruido de espectro plano."""
        blanco = np.random.default_rng(7).standard_normal(SR * 12)
        _, db = self.niveles(self.escribir(blanco))
        self.assertAlmostEqual(self.pendiente(db), 1.0, delta=0.06)

    def test_ruido_rosa_sale_plano(self):
        """El rosa tiene potencia constante por octava — y por tercio."""
        blanco = np.random.default_rng(11).standard_normal(SR * 12)
        X = np.fft.rfft(blanco)
        f = np.fft.rfftfreq(len(blanco), 1 / SR)
        X[1:] /= np.sqrt(f[1:])
        X[0] = 0
        rosa = np.fft.irfft(X, n=len(blanco))
        _, db = self.niveles(self.escribir(rosa))
        self.assertAlmostEqual(self.pendiente(db), 0.0, delta=0.06)

    def test_un_tono_cae_en_su_banda_y_no_en_la_vecina(self):
        t = np.arange(SR * 12) / SR
        r, _ = self.niveles(self.escribir(np.sin(2 * np.pi * 1000 * t)))
        vivas = [b for b in r["bandas"] if b["db"] is not None]
        orden = sorted(vivas, key=lambda b: -b["db"])
        self.assertEqual(orden[0]["hz"], 1000)
        # La separación con la siguiente banda tiene que ser enorme, no de un
        # par de dB: si no, el filtrado por banda está goteando.
        self.assertGreater(orden[0]["db"] - orden[1]["db"], 40)

    def test_la_ponderacion_hunde_el_grave_y_respeta_el_medio(self):
        """La curva A vale ~0 dB en 1 kHz por definición y −50 dB en 20 Hz."""
        blanco = np.random.default_rng(3).standard_normal(SR * 12)
        ruta = self.escribir(blanco)
        r = _espectro_tercios_octava(ruta, 0, 12, ponderacion_a)
        por_hz = {b["hz"]: b for b in r["bandas"]}
        # El desplazamiento de cada banda al ponderar, relativo al de 1 kHz.
        def desplazamiento(hz):
            return ((por_hz[hz]["db_pond"] - por_hz[hz]["db"])
                    - (por_hz[1000]["db_pond"] - por_hz[1000]["db"]))
        self.assertLess(desplazamiento(20), -45)       # tabla IEC: −50.4 dB
        self.assertLess(desplazamiento(100), -18)      # tabla IEC: −19.1 dB
        self.assertAlmostEqual(desplazamiento(1000), 0.0, delta=0.01)
        self.assertGreater(desplazamiento(2500), 0.5)  # tabla IEC: +1.3 dB


class TestElAnchoDeBandaEsHonesto(Base):
    """El motivo de fondo por el que existe esta medida."""

    def test_un_archivo_de_44k_llega_a_20_khz(self):
        blanco = np.random.default_rng(5).standard_normal(SR * 12)
        r, _ = self.niveles(self.escribir(blanco))
        vivas = [b["hz"] for b in r["bandas"] if b["db"] is not None]
        self.assertEqual(max(vivas), 20000)
        self.assertEqual(r["techo_hz"], SR // 2)

    def test_lo_que_esta_sobre_nyquist_se_devuelve_vacio_no_inventado(self):
        """Un archivo a 22.05 kHz no tiene nada por encima de 11 kHz. Antes el
        gráfico dibujaba ahí una curva; ahora la banda vale None y la interfaz
        sombrea la zona."""
        blanco = np.random.default_rng(5).standard_normal(22050 * 12)
        r = _espectro_tercios_octava(self.escribir(blanco, 22050), 0, 12, sin_ponderar)
        nulas = [b["hz"] for b in r["bandas"] if b["db"] is None]
        self.assertEqual(nulas, [12500, 16000, 20000])
        self.assertEqual(r["techo_hz"], 11025)

    def test_las_31_bandas_estan_siempre(self):
        """Aunque estén vacías: la interfaz cuenta con la lista completa."""
        blanco = np.random.default_rng(5).standard_normal(8000 * 12)
        r = _espectro_tercios_octava(self.escribir(blanco, 8000), 0, 12, sin_ponderar)
        self.assertEqual(len(r["bandas"]), 31)
        self.assertEqual([b["hz"] for b in r["bandas"]], _CENTROS_TERCIO)

    def test_el_grave_no_se_queda_sin_medir(self):
        """Las bandas graves son estrechísimas — la de 25 Hz mide 5.7 Hz — y
        cuando el archivo es corto la FFT se acorta con él y deja de tener bins
        ahí dentro. Sin la red del bin más cercano, esas bandas saldrían al
        suelo de la escala: un agujero dibujado como "aquí no hay nada".

        Se fuerza con un archivo corto, que es cuando pasa de verdad: a 44.1 kHz
        con la FFT completa no se queda vacía ninguna."""
        corto = np.random.default_rng(9).standard_normal(3000)   # n_fft = 2048
        r, _ = self.niveles(self.escribir(corto), dur=1)
        por_hz = {b["hz"]: b["db"] for b in r["bandas"]}
        suelo = min(v for v in por_hz.values() if v is not None)
        for hz in (25, 31.5, 50):
            self.assertIsNotNone(por_hz[hz], f"hueco en {hz} Hz")
            self.assertGreater(
                por_hz[hz], suelo + 1.0,
                f"la banda de {hz} Hz salió al suelo: se quedó sin bins y "
                f"nadie la rescató")

    def test_cada_tono_cae_en_la_banda_que_lleva_su_nombre(self):
        """Pincha el mapeo entero banda→frecuencia, no solo un punto. Un
        desplazamiento de un índice lo revienta.

        No distingue centros en base 10 de centros en base 2: divergen un 1.35 %
        y la banda mide ±12.2 %. IEC 61260 admite las dos, así que no es algo
        que este test deba tener opinión sobre."""
        t = np.arange(SR * 4) / SR
        for hz in (50, 125, 500, 1000, 4000, 10000):
            ruta = self.escribir(np.sin(2 * np.pi * hz * t))
            r, _ = self.niveles(ruta, dur=4)
            vivas = [b for b in r["bandas"] if b["db"] is not None]
            ganadora = max(vivas, key=lambda b: b["db"])
            self.assertEqual(ganadora["hz"], hz,
                             f"un tono de {hz} Hz cayó en la banda de "
                             f"{ganadora['hz']} Hz")


class TestNoRevientaNunca(Base):
    """Es un gráfico. Ningún archivo raro puede tumbar el análisis entero."""

    def comprobar_se_rinde(self, ruta):
        r = _espectro_tercios_octava(ruta, 0, 10, sin_ponderar)
        self.assertEqual(r, {}, "debería devolver {} para caer a las 6 bandas")

    def test_ruta_inexistente(self):
        self.comprobar_se_rinde("/no/existe/de/verdad.wav")

    def test_un_archivo_que_no_es_audio(self):
        self.comprobar_se_rinde(os.path.abspath(__file__))

    def test_archivo_mas_corto_que_una_trama(self):
        self.comprobar_se_rinde(self.escribir(np.zeros(200) + 1e-3))

    def test_el_silencio_no_finge_un_balance_perfecto(self):
        """Sin energía, la cuota de cada banda sale igual y el gráfico dibujaba
        una recta impecable. Se prefiere no dibujar."""
        ruta = tempfile.mktemp(suffix=".wav")
        self.temporales.append(ruta)
        sf.write(ruta, np.zeros(SR * 3, dtype="float32"), SR)
        self.comprobar_se_rinde(ruta)

    def test_una_ventana_fuera_del_archivo_usa_el_archivo_entero(self):
        """El drop se calcula sobre el track remuestreado; si por redondeo cae
        más allá del final, no puede quedarse sin datos."""
        blanco = np.random.default_rng(2).standard_normal(SR * 12)
        r = _espectro_tercios_octava(self.escribir(blanco), 900, 910, sin_ponderar)
        self.assertTrue(r["bandas"])

    def test_lee_los_dos_canales_no_solo_el_izquierdo(self):
        """Es un balance tonal, así que los canales se suman a mono. Con una
        señal distinta en cada lado — grave a la izquierda, agudo a la derecha —
        el resultado tiene que llevar las dos; quedarse con un canal se
        comería medio espectro.

        Antes esto se probaba con L y R idénticos, que es exactamente el caso
        en el que leer un solo canal da el resultado correcto."""
        t = np.arange(SR * 6) / SR
        izq = np.sin(2 * np.pi * 100 * t)      # solo grave
        der = np.sin(2 * np.pi * 5000 * t)     # solo agudo
        ruta = tempfile.mktemp(suffix=".wav")
        self.temporales.append(ruta)
        sf.write(ruta, (np.column_stack([izq, der]) * 0.4).astype("float32"), SR)
        r, _ = self.niveles(ruta, dur=6)
        por_hz = {b["hz"]: b["db"] for b in r["bandas"]}
        suelo = min(v for v in por_hz.values() if v is not None)
        self.assertGreater(por_hz[100], suelo + 40, "se perdió el canal izquierdo")
        self.assertGreater(por_hz[5000], suelo + 40, "se perdió el canal derecho")


class TestLlegaAlDiagnostico(unittest.TestCase):
    def test_el_orquestador_lo_pasa(self):
        ruta = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "engine", "diagnostico.py")
        with open(ruta, encoding="utf-8") as f:
            self.assertIn('"espectro_fino": senales.get("espectro_fino"', f.read())

    def test_el_extractor_lo_publica(self):
        ruta = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "engine", "extractor.py")
        with open(ruta, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"espectro_fino": espectro_fino,', src)
        # Y la medida vieja de 6 bandas que leen las reglas NO se ha tocado.
        self.assertIn('"espectro_bandas": espectro_bandas,', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
