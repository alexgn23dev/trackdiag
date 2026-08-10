"""Nada de jerga interna en el texto que lee el productor.

Origen: la primera prioridad de `problema_arreglo` decía «n_bloques bajo».
`n_bloques` es el nombre de una variable del extractor. Para quien no ha visto
el código no significa nada, y encima transmite que el informe está sin
terminar.

Es un fallo fácil de repetir: el motor tiene decenas de señales con nombre
técnico, y al escribir un texto explicando qué las dispara sale sola la
tentación de nombrarlas. Estos tests barren TODO el texto de cara al usuario
—plantillas y un diagnóstico generado de verdad— buscando esos nombres.
"""

import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import templates as T  # noqa: E402
from engine.diagnostico import generar_diagnostico  # noqa: E402
from engine.extractor import extraer_senales  # noqa: E402
from tests import fixtures as fx  # noqa: E402

# Nombres de variables y claves internas. Se buscan como palabra completa para
# no marcar prosa legítima ("el rango dinámico" sí, `rango_dinamico` no).
JERGA = re.compile(
    r"\b("
    r"n_bloques|varianza_energia|contraste_energetico|densidad_espectral|"
    r"diff_[a-z_]+|db_[a-z]+|ratio_[a-z_]+|max_seccion_[a-z]+|pct_[a-z_]+|"
    r"lufs_[a-z]+|true_peak_[a-z_]+|sample_peak_[a-z_]+|racha_[a-z_]+|"
    r"categoria_[a-z]+|severidad_[a-z]+|nivel_[a-z_]+|aviso_[a-z_]+|"
    r"muestras_en_techo[a-z_]*|concentracion_en_[a-z_]+|"
    r"estado_track|madurez_estimada|tiene_desarrollo|break_sin_payoff|"
    r"archivo_[a-z_]+|peak_[a-z_]+|senales|datos_audio"
    r")\b"
)

# Campos del diagnóstico que el usuario LEE. Se excluyen a propósito los que
# son identificadores (`id`, `estado_track`) o diccionarios de datos crudos.
CAMPOS_VISIBLES = [
    "prioridades", "no_tocar_aun", "sugerencias_estructura", "siguiente_sesion",
    "nota_contextual", "tips_genero", "tip_objetivo", "referencia_temporal",
    "nota_motivacional", "disclaimer", "aviso_genero", "alcance_analisis",
    "estado_texto", "error_de_foco_mensaje",
]

CONTEXTOS = [
    {"genero": "techno", "fase": "boceto", "objetivo": "aprender",
     "experiencia": "0-2", "dificultad_habitual": "estructura"},
    {"genero": "techno", "fase": "casi_listo", "objetivo": "sellos",
     "experiencia": "2-5", "dificultad_habitual": "mezcla"},
    {"genero": "house", "fase": "mezclando", "objetivo": "publicar",
     "experiencia": "5+", "dificultad_habitual": "mastering"},
]

_DIR = tempfile.mkdtemp(prefix="mentotrack_lenguaje_")
_MANIFIESTO = None
_CACHE = {}


def setUpModule():
    global _MANIFIESTO
    _MANIFIESTO = fx.generar(_DIR, solo=["wav24_pico_menos1", "wav24_clipping_evidente",
                                         "wav24_clip_sostenido"])


def senales(nombre):
    if nombre not in _CACHE:
        _CACHE[nombre] = extraer_senales(_MANIFIESTO[nombre]["ruta"])
    return _CACHE[nombre]


def recorrer(obj, ruta=""):
    """Devuelve (ruta, palabra, contexto) por cada fuga encontrada."""
    if isinstance(obj, str):
        m = JERGA.search(obj)
        if m:
            i = max(0, m.start() - 60)
            yield ruta, m.group(0), obj[i:m.end() + 60]
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from recorrer(v, f"{ruta}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from recorrer(v, f"{ruta}[{i}]")


class TestPlantillas(unittest.TestCase):
    def test_sin_nombres_de_variables(self):
        fugas = list(recorrer(T.TEMPLATES, "TEMPLATES"))
        detalle = "\n".join(f"  {r}: «{p}» → …{c}…" for r, p, c in fugas)
        self.assertEqual(fugas, [], f"\n{detalle}")

    def test_el_caso_que_lo_motivo_sigue_arreglado(self):
        texto = " ".join(T.TEMPLATES["problema_arreglo"]["prioridades"])
        self.assertNotIn("n_bloques", texto)
        # Y la idea que quería transmitir sigue estando, en castellano
        self.assertIn("secciones", texto)


class TestDiagnosticoGenerado(unittest.TestCase):
    """Las plantillas no son todo: contextualizador.py y extractor.py también
    escriben texto, y ahí es donde es más fácil que se cuele una clave."""

    def _visibles(self, r):
        return {k: r[k] for k in CAMPOS_VISIBLES if k in r}

    def test_ningun_contexto_produce_jerga(self):
        fugas = []
        for nombre in _MANIFIESTO:
            for ctx in CONTEXTOS:
                r = generar_diagnostico(senales(nombre), dict(ctx, genero_custom="",
                                                              bloqueo_percibido=""))
                fugas += [(f"{nombre}/{ctx['fase']}{ruta}", p, c)
                          for ruta, p, c in recorrer(self._visibles(r))]
        detalle = "\n".join(f"  {r}: «{p}» → …{c}…" for r, p, c in fugas)
        self.assertEqual(fugas, [], f"\n{detalle}")

    def test_los_textos_de_picos_tampoco(self):
        for nombre in _MANIFIESTO:
            lo = senales(nombre)["loudness"]
            visible = {k: lo[k] for k in
                       ("titulo_picos", "aviso_picos", "nota_lossy_picos",
                        "titulo_recorte", "aviso_recorte", "referencia",
                        "consejo_master", "aviso_saturacion")
                       if k in lo}
            fugas = list(recorrer(visible, nombre))
            detalle = "\n".join(f"  {r}: «{p}» → …{c}…" for r, p, c in fugas)
            self.assertEqual(fugas, [], f"\n{detalle}")


class TestElBarridoDetectaDeVerdad(unittest.TestCase):
    """Un test que nunca puede fallar no protege de nada."""

    def test_pilla_una_fuga_inventada(self):
        falso = {"prioridades": ["Sube el nivel si n_bloques bajo."]}
        self.assertEqual(len(list(recorrer(falso))), 1)

    def test_no_marca_prosa_legitima(self):
        """Las mismas ideas escritas en castellano no deben saltar."""
        bueno = {"prioridades": [
            "El rango dinámico es bajo y el contraste entre secciones también.",
            "Tu track tiene pocas secciones y el true peak se pasa del techo.",
            "Revisa la densidad espectral en los medios.",
        ]}
        self.assertEqual(list(recorrer(bueno)), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
