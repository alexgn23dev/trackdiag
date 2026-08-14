"""El análisis de estructura tiene que aguantar un BPM equivocado.

## Por qué existe

El motor parte el track en bloques de ~8 compases usando el BPM detectado. Si
el BPM está mal, los cortes caen en sitios equivocados.

En material típico eso no cambia el diagnóstico: medido sobre 9 tracks reales
con errores forzados de ±25 %, 8 dan el mismo diagnóstico y estado. El caso
que lo destapó —un track a 140 leído como 112— dio exactamente el mismo
diagnóstico que con el BPM correcto.

**Pero la tolerancia NO es universal.** Probando variantes sintéticas se
encuentran dos zonas donde sí se rompe:

  · **tracks cortos** (~1:30): a −25 % el diagnóstico salta de
    `carencia_espectral` a `mezcla_prematura`;
  · **secciones muy cortas** (~12 s): cambian el estado y el contraste.

Es decir: el margen existe pero no es infinito, y por eso este guard tiene
dientes. Si alguien hace el motor MÁS dependiente del tempo, los casos
típicos —que hoy están cómodamente dentro— empezarán a moverse y saltará
aquí.

## Por qué hace falta un guard automático

Desde v0.5.99 el BPM ya no se le enseña al usuario. Antes, cuando el detector
fallaba, el usuario lo veía en pantalla y se quejaba — así se descubrió el
caso de los 140. Ahora el fallo es invisible: si además dejara de ser
inofensivo, tendríamos diagnósticos torcidos sin ninguna señal de alarma.
Este test sustituye a ese ojo humano.

## Qué NO comprueba

Que el BPM sea correcto (no lo es: solo el 15 % de los tracks de usuario pasan
el filtro de confianza, ver docs/bpm-por-que-no-se-ensena.md). Comprueba que,
en material típico, dé igual.
"""

import os
import sys
import tempfile
import unittest
import warnings

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

from engine.diagnostico import generar_diagnostico  # noqa: E402
from engine.extractor import extraer_senales  # noqa: E402

SR = 22050
BPM_BASE = 128
# El desvío del caso real (140 leído como 112 = 25 %) y su simétrico.
DESVIOS = (0.75, 0.80, 1.25)

CONTEXTO = {
    "genero": "techno", "fase": "casi_listo", "objetivo": "sellos",
    "experiencia": "2-5", "dificultad_habitual": "mezcla",
    "bloqueo_percibido": "",
}


def _track_con_estructura(bpm=BPM_BASE, dur=200, secc=25.0, contraste=0.45):
    """Un track de club sintético CON estructura: bloques de energía alta y
    baja alternos, que es lo que el análisis de secciones tiene que leer.

    Sintético a propósito: el test no puede depender de los archivos de Alex,
    y así es determinista y rápido.
    """
    n = int(SR * dur)
    y = np.zeros(n)
    spb = 60.0 / bpm
    rng = np.random.default_rng(11)

    tk = np.arange(int(SR * 0.12)) / SR
    kick = np.sin(2 * np.pi * np.cumsum(np.linspace(120, 45, len(tk))) / SR) * np.exp(-tk * 26)
    largo_h = int(SR * 0.05)
    hat = rng.standard_normal(largo_h) * np.exp(-np.arange(largo_h) / SR * 90) * 0.25

    # Secciones alternas drop / break / drop / break…
    seccion = secc
    for i in range(int(dur / spb)):
        t = i * spb
        fuerte = int(t / seccion) % 2 == 0
        p = int(t * SR)
        if p + len(kick) < n:
            y[p:p + len(kick)] += kick * (0.95 if fuerte else contraste * 0.95)
        ph = int((t + spb / 2) * SR)
        if ph + len(hat) < n and fuerte:
            y[ph:ph + len(hat)] += hat
    tt = np.arange(n) / SR
    energia = np.where((tt // seccion).astype(int) % 2 == 0, 1.0, contraste)
    y += 0.20 * np.sin(2 * np.pi * 55 * tt) * energia
    y += 0.05 * np.sin(2 * np.pi * 900 * tt) * energia
    return (y / np.max(np.abs(y)) * 0.7).astype(np.float32)


def _analizar(ruta, bpm):
    s = extraer_senales(ruta, bpm_manual=bpm, omitir_armonia=True)
    d = generar_diagnostico(s, CONTEXTO)
    return {
        "diagnostico": d["diagnostico_principal"]["id"],
        "estado": d.get("estado_track"),
        "contraste": s.get("contraste_energetico"),
        "desarrollo": s.get("tiene_desarrollo"),
        "estructura_problematica": (s.get("distribucion") or {}).get("estructura_problematica"),
    }


# Variantes TÍPICAS: duración y secciones de un track de club normal, que es
# donde la tolerancia se ha medido y se sostiene. Se usan varias porque una
# sola tiene demasiada holgura: con un único caso cómodo, un guard así pasa
# aunque se haya roto la tolerancia (comprobado — el primer intento de este
# test no detectaba un sabotaje real).
VARIANTES = {
    "estructura clara": dict(),
    "contraste bajo": dict(contraste=0.80),
    "secciones largas": dict(secc=45.0),
    "casi plano": dict(contraste=0.93),
}


class TestUnBpmMaloNoCambiaElDiagnostico(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import soundfile as sf
        cls.rutas, cls.correcto = {}, {}
        for etiqueta, kw in VARIANTES.items():
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                sf.write(f.name, _track_con_estructura(**kw), SR)
                cls.rutas[etiqueta] = f.name
            cls.correcto[etiqueta] = _analizar(f.name, BPM_BASE)

    @classmethod
    def tearDownClass(cls):
        for r in cls.rutas.values():
            os.unlink(r)

    def test_las_variantes_tienen_estructura_que_leer(self):
        """Si el audio sintético saliera plano, los demás tests pasarían por no
        medir nada. Esta es la comprobación de que el test tiene sentido."""
        for etiqueta, base in self.correcto.items():
            self.assertIsNotNone(base["diagnostico"], etiqueta)
            self.assertIn(base["contraste"], ("bajo", "medio", "alto"), etiqueta)

    def test_el_diagnostico_aguanta_desvios_de_hasta_25_por_ciento(self):
        """El caso real fue del 25 % (140 leído como 112) y dio el mismo
        diagnóstico. Si esto falla, un fallo del detector —que ya no se ve en
        pantalla— habrá empezado a torcer diagnósticos en silencio."""
        fallos = []
        for etiqueta, ruta in self.rutas.items():
            for factor in DESVIOS:
                malo = int(round(BPM_BASE * factor))
                r = _analizar(ruta, malo)
                if r["diagnostico"] != self.correcto[etiqueta]["diagnostico"]:
                    fallos.append(f"«{etiqueta}» con {malo} BPM (real {BPM_BASE}): "
                                  f"{self.correcto[etiqueta]['diagnostico']} → {r['diagnostico']}")
        self.assertEqual(fallos, [], "\n  " + "\n  ".join(fallos))

    def test_el_estado_del_track_tampoco_cambia(self):
        """El estado (verde / en desarrollo / avanzado) es lo primero que lee
        el usuario, y sale de las mismas señales de estructura."""
        fallos = []
        for etiqueta, ruta in self.rutas.items():
            for factor in DESVIOS:
                malo = int(round(BPM_BASE * factor))
                r = _analizar(ruta, malo)
                if r["estado"] != self.correcto[etiqueta]["estado"]:
                    fallos.append(f"«{etiqueta}» con {malo} BPM: "
                                  f"{self.correcto[etiqueta]['estado']} → {r['estado']}")
        self.assertEqual(fallos, [], "\n  " + "\n  ".join(fallos))

    def test_las_senales_de_estructura_se_mantienen(self):
        """Desarrollo y estructura_problematica alimentan la jerarquía de
        diagnósticos: si se mueven, el orden de prioridades se mueve con ellas.

        El contraste NO se comprueba: medido sobre material real es la señal
        que llega a moverse (medio → alto en 1 de 9 tracks), y exigirle
        inmunidad sería pedir más de lo que se ha demostrado.
        """
        fallos = []
        for etiqueta, ruta in self.rutas.items():
            for factor in DESVIOS:
                malo = int(round(BPM_BASE * factor))
                r = _analizar(ruta, malo)
                for clave in ("desarrollo", "estructura_problematica"):
                    if r[clave] != self.correcto[etiqueta][clave]:
                        fallos.append(f"«{etiqueta}» {clave} con {malo} BPM: "
                                      f"{self.correcto[etiqueta][clave]} → {r[clave]}")
        self.assertEqual(fallos, [], "\n  " + "\n  ".join(fallos))


class TestLaSuposicionEstaDocumentada(unittest.TestCase):
    def test_el_codigo_dice_que_el_reparto_depende_del_tempo(self):
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "engine", "extractor.py"), encoding="utf-8").read()
        self.assertIn("duracion_bloque_seg = (60.0 / tempo) * beats_por_bloque", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
