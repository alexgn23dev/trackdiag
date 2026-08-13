"""Mentotrack solo analiza electrónica de club.

Decisión de producto (ago-2026): cuando alguien marca "Otro" y escribe un
género que no es electrónica —rock, jazz, flamenco, reggae, trap, balkan,
pop, reggaetón…— el análisis se rechaza en vez de darlo con un aviso al pie.
Fuera del club el motor no mide peor: mide OTRA COSA (el corredor espectral,
las normas de estructura y las referencias de loudness son todas de club).

Lo que estos tests protegen, por orden de importancia:

  1. **Que no se rechace a quien sí hace electrónica.** Es el error caro: una
     puerta cerrada en la cara. El listado de control sale de los 196 géneros
     que la gente ha escrito de verdad en producción.
  2. Que lo que Alex no quiere, no pase.
  3. Que el desplegable no se toque nunca.
  4. Que las listas del backend y del frontend no diverjan.
"""

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.generos import (  # noqa: E402
    GENEROS_ELECTRONICOS,
    GENEROS_NO_ELECTRONICOS,
    fuera_de_alcance,
)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(os.path.dirname(RAIZ), "frontend", "index.html")


def _rechaza(custom):
    return fuera_de_alcance("otro", custom)[0]


class TestNoSeRechazaAQuienHaceElectronica(unittest.TestCase):
    """El error caro. Todos estos los escribió alguien de verdad."""

    ELECTRONICA_REAL = [
        # subgéneros que el desplegable no tiene
        "hardgroove", "schranz", "makina", "newstyle", "bounce", "hard bounce",
        "uk garage", "deep uk garage", "nu disco", "dark disco", "bass house",
        "glitch house", "funky house", "organic house", "melodic house",
        "minimal deep tech", "hypnotic techno", "raw techno", "peak time techno",
        "drum and bass", "d&b ragga jungle", "dnb neurofunk", "jungle",
        "dubstep", "breakbeat", "progressive breaks", "idm", "ebm",
        "acid techno", "darkpsy, psytrance", "psytech", "electro house",
        "guaracha", "amapiano", "hypnotic afro", "afro tech house",
        "eurodance", "electronica experimental", "midtempo bass", "phonk",
        # mezclas con una palabra no electrónica: el marcador electrónico manda
        "afro house, urban, pop", "edm, disco, funky, pop",
        "uk garage, con algo de trap", "hip hop, electronic",
        "breaks,hard trance,percusion asiatica,techno",
        # escritos raro, pero electrónica
        "musica electro", "tekno", "electronic", "dance",
    ]

    def test_ninguno_se_rechaza(self):
        rechazados = [g for g in self.ELECTRONICA_REAL if _rechaza(g)]
        self.assertEqual(rechazados, [], f"falsos rechazos: {rechazados}")

    def test_lo_que_no_se_reconoce_pasa(self):
        """Los subgéneros se inventan cada temporada. Ante la duda, se acepta:
        un informe flojo se puede ignorar, una puerta cerrada no."""
        for g in ("techengue", "bochka", "hardbounce", "fucktechno", "chunflinflan"):
            self.assertFalse(_rechaza(g), g)


class TestLoQueNoEntra(unittest.TestCase):
    FUERA = [
        "rock", "jazz", "flamenco", "reggae", "trap", "balkan beat", "pop",
        "reggaeton", "regueton", "rap", "hip hop", "cumbia peruana", "metal",
        "blues rock", "kpop", "drill", "merengue", "vallenato", "bolero",
        "bosa nova", "afrobeat", "new age", "indie rock", "punk rock",
        "swing jazz", "gospel", "dembow", "reparto", "folclore", "clasica",
        "experimental arabe balkan", "upbeat anime ost",
    ]

    def test_se_rechazan(self):
        pasan = [g for g in self.FUERA if not _rechaza(g)]
        self.assertEqual(pasan, [], f"deberían rechazarse: {pasan}")

    def test_no_salta_dentro_de_otra_palabra(self):
        """La lista de fuera casa por PALABRA: "rap" no puede saltar dentro de
        "rapsodia" ni "pop" dentro de otra cosa."""
        self.assertFalse(_rechaza("rapsodia electronica"))
        self.assertFalse(_rechaza("poppy techno"))


class TestElDesplegableNoSeToca(unittest.TestCase):
    def test_los_generos_del_catalogo_nunca_se_rechazan(self):
        for g in ("techno", "tech_house", "house", "trance", "minimal",
                  "melodic_techno", "afro_house", "hard_techno", "progressive_house"):
            self.assertFalse(fuera_de_alcance(g, "")[0], g)

    def test_otro_sin_texto_no_se_juzga(self):
        """El formulario ya exige el texto; aquí no se inventa un rechazo por
        un dato que falta."""
        self.assertFalse(fuera_de_alcance("otro", "")[0])
        self.assertFalse(fuera_de_alcance("otro", " ")[0])


class TestElFrontendNoDiverge(unittest.TestCase):
    """Las listas están duplicadas (backend autoritativo, frontend para avisar
    antes de subir). Duplicar es aceptable; divergir no."""

    def setUp(self):
        self.html = open(INDEX, encoding="utf-8").read()

    def _lista(self, nombre):
        i = self.html.index(f"const {nombre} = [")
        j = self.html.index("];", i)
        crudo = self.html[i + len(f"const {nombre} = ["):j]
        # El bloque va partido en varias líneas: JSON no admite saltos crudos
        # dentro del array tal cual salen del fichero.
        crudo = " ".join(crudo.split()).strip().rstrip(",")
        return json.loads("[" + crudo + "]")

    def test_la_lista_electronica_coincide(self):
        self.assertEqual(self._lista("GENEROS_ELECTRONICOS"), GENEROS_ELECTRONICOS)

    def test_la_lista_no_electronica_coincide(self):
        self.assertEqual(self._lista("GENEROS_NO_ELECTRONICOS"), GENEROS_NO_ELECTRONICOS)

    def test_ningun_literal_partido_en_dos_lineas(self):
        """Un literal partido rompe el JavaScript de TODA la app, y el test de
        sincronía de arriba no lo ve (normaliza los espacios antes de comparar,
        así que recompone lo roto). Pasó de verdad al generar estas listas:
        "hard dance" quedó como "hard\n dance" y la página entera dejó de
        arrancar mientras los tests seguían en verde."""
        for nombre in ("GENEROS_ELECTRONICOS", "GENEROS_NO_ELECTRONICOS"):
            i = self.html.index(f"const {nombre} = [")
            j = self.html.index("];", i)
            for k, linea in enumerate(self.html[i:j].split("\n")):
                self.assertEqual(
                    linea.count('"') % 2, 0,
                    f"{nombre}, línea {k}: comillas sin cerrar → JS roto\n  {linea.strip()}")

    def test_el_formulario_bloquea_de_verdad(self):
        """No basta con avisar: el cuestionario no puede avanzar."""
        self.assertIn("&& !esGeneroNoElectronico((contexto.genero_custom || '').trim())", self.html)

    def test_el_backend_rechaza_antes_de_leer_el_audio(self):
        src = open(os.path.join(RAIZ, "main.py"), encoding="utf-8").read()
        i = src.index("GENERO_FUERA_DE_ALCANCE")
        j = src.index("content = await audio.read()")
        self.assertLess(i, j, "se rechaza después de leer el archivo: le hacemos subirlo para nada")
        self.assertIn("status_code=422", src[max(0, i - 200):i + 200])


class TestElEndpointRechaza(unittest.TestCase):
    def test_422_con_codigo_estable(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi.testclient no disponible")
        os.environ.setdefault("JWT_SECRET", "test")
        os.environ.setdefault("ADMIN_KEY", "test")
        import main
        with TestClient(main.app) as c:
            r = c.post("/api/diagnostico",
                       files={"audio": ("x.wav", b"RIFF" + b"\x00" * 64, "audio/wav")},
                       data={"genero": "otro", "genero_custom": "reggaeton",
                             "fase": "casi_listo", "objetivo": "sellos",
                             "experiencia": "2-5", "dificultad_habitual": "mezcla"})
        self.assertEqual(r.status_code, 422, r.text[:200])
        cuerpo = r.json()
        self.assertEqual(cuerpo["codigo"], "GENERO_FUERA_DE_ALCANCE")
        self.assertIn("electrónica de club", cuerpo["error"])
        self.assertNotIn("datos_audio", cuerpo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
