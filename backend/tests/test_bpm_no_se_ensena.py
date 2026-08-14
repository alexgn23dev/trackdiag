"""El BPM no se le afirma al usuario en ninguna parte del informe.

Decisión de Alex (14-ago-2026): si no podemos acertar casi siempre, mejor no
dar el dato. Los números que la sostienen, medidos y no estimados:

  · el detector solo pasa su filtro de confianza en el **15 %** de los tracks
    de usuario reales (5 de 33) — en previews ya masterizados, el 42 %;
  · antes del refinado, el **95 %** de los BPM que dábamos caían en un bin del
    tempograma y el **0 %** en un BPM de productor;
  · el valor más frecuente era **129**, en el 40 % de los análisis: el bin
    donde caen 128 y 130, que son los dos tempos más comunes del género.

El BPM se sigue calculando —lo usa el reparto en bloques de ~8 compases— y se
sigue publicando en `datos_audio`. Lo que no se hace es enseñárselo.

Detalle completo y las dos vías para recuperarlo:
docs/bpm-por-que-no-se-ensena.md
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(os.path.dirname(RAIZ), "frontend", "index.html")


def _fuente(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


class TestElInformeNoAfirmaUnBpm(unittest.TestCase):
    """Sobre el frontend: los sitios donde SÍ puede aparecer un BPM son el
    formulario de la comunidad (lo escribe el usuario), el historial de
    análisis antiguos (ya guardados con su BPM) y el texto del informe que se
    archiva en la DB. En el informe en pantalla, no."""

    def setUp(self):
        self.html = _fuente(INDEX)

    def test_no_hay_chip_de_bpm_en_la_cabecera(self):
        i = self.html.index("const cfgV2 = r.estado_track")
        j = self.html.index("V2_TABS.map", i)
        self.assertNotIn('etiqueta="BPM"', self.html[i:j],
                         "ha vuelto el chip de BPM a la cabecera del informe")

    def test_no_hay_fila_de_bpm_en_el_detalle(self):
        i = self.html.index('<V2Tarjeta titulo="Estructura">')
        j = self.html.index("</V2Tarjeta>", i)
        self.assertNotIn("BPM", self.html[i:j])

    def test_la_pantalla_de_analisis_no_canta_un_bpm(self):
        i = self.html.index("function ProcessingScreen(")
        j = self.html.index("\n    }", i)
        self.assertNotIn("BPM", self.html[i:j])

    def test_el_campo_de_la_comunidad_no_se_prerrellena_a_ciegas(self):
        """Ahí el BPM sí aparece —lo publica el usuario junto a su track— pero
        solo se pre-rellena cuando el detector pasó su filtro."""
        self.assertIn("d.tempo_refinado && d.bpm ? String(d.bpm) : ''", self.html)


class TestElMotorNoDerivaTextosDelBpm(unittest.TestCase):
    """Un número derivado de un dato malo hereda el error y además lo esconde:
    el usuario ve segundos y no ve de dónde salen."""

    def setUp(self):
        self.src = _fuente(os.path.join(RAIZ, "engine", "contextualizador.py"))

    def test_no_se_construyen_frases_con_bpm(self):
        vivos = [ln.strip() for ln in self.src.split("\n")
                 if "BPM" in ln
                 and not ln.strip().startswith("#")
                 and "patron" not in ln and "nota" not in ln]
        self.assertEqual(vivos, [],
                         f"vuelven a emitirse textos con BPM: {vivos}")

    def test_el_consejo_del_drop_sobrevive_sin_la_cifra(self):
        """El consejo vale igual en compases: no depende de acertar el tempo."""
        self.assertIn("últimos 4 compases antes del drop", self.src)


class TestLoQueSeConserva(unittest.TestCase):
    def test_el_bpm_se_sigue_calculando_y_publicando(self):
        """El reparto en bloques lo usa, y el formulario de la comunidad lo
        ofrece. Retirarlo del cálculo sería otra decisión, más cara."""
        src = _fuente(os.path.join(RAIZ, "engine", "diagnostico.py"))
        self.assertIn('"bpm": senales.get("bpm")', src)
        self.assertIn('"tempo_refinado"', src)

    def test_el_reparto_en_bloques_sigue_usando_el_tempo(self):
        src = _fuente(os.path.join(RAIZ, "engine", "extractor.py"))
        self.assertIn("duracion_bloque_seg = (60.0 / tempo) * beats_por_bloque", src)

    def test_relesit_solo_recibe_el_bpm_cuando_es_fiable(self):
        html = _fuente(INDEX)
        self.assertIn("bpm: bpmFiable || null", html)
        self.assertIn("d.tempo_refinado ? d.bpm : null", html)


class TestLaDecisionEstaDocumentada(unittest.TestCase):
    def test_los_numeros_estan_junto_al_codigo(self):
        src = _fuente(os.path.join(RAIZ, "engine", "contextualizador.py"))
        self.assertIn("15 %", src)
        self.assertIn("docs/bpm-por-que-no-se-ensena.md", src)

    def test_existe_la_nota(self):
        doc = os.path.join(os.path.dirname(RAIZ), "docs", "bpm-por-que-no-se-ensena.md")
        if not os.path.exists(doc):
            self.skipTest("docs/ no viaja en la imagen de producción")
        texto = _fuente(doc)
        for dato in ("15 %", "95 %", "129"):
            self.assertIn(dato, texto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
