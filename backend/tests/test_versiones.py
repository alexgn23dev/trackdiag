"""Versionado de algoritmos y dependencias.

Sin esto, dos análisis del mismo archivo pueden dar números distintos y no hay
forma de saber por qué. Los tests comprueban que cada análisis lleva pegado
con qué se midió, y que las dependencias que determinan las mediciones están
fijadas a una versión exacta.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.versiones import (  # noqa: E402
    ANALYSIS_ENGINE_VERSION, LOUDNESS_ALGORITHM_VERSION, PEAK_ALGORITHM_VERSION,
    algoritmos, dependencias,
)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestConstantes(unittest.TestCase):
    def test_no_estan_vacias(self):
        for nombre, valor in algoritmos().items():
            self.assertTrue(valor and isinstance(valor, str), nombre)

    def test_identifican_el_metodo(self):
        self.assertIn("soxr_hq_8x", PEAK_ALGORITHM_VERSION,
                      "la versión del algoritmo de picos debe nombrar el método "
                      "y el factor de sobremuestreo")
        self.assertIn("pyloudnorm", LOUDNESS_ALGORITHM_VERSION)
        self.assertTrue(ANALYSIS_ENGINE_VERSION.startswith("engine-"))

    def test_loudness_subio_tras_el_arreglo_del_mono(self):
        """v0.5.71 cambió cómo se mide un archivo mono: los análisis anteriores
        no son comparables y la versión tiene que reflejarlo."""
        self.assertTrue(LOUDNESS_ALGORITHM_VERSION.endswith("-2"),
                        "el arreglo del mono exige subir la versión de loudness")


class TestDependencias(unittest.TestCase):
    CRITICAS = ["numpy", "scipy", "soundfile", "soxr", "librosa", "pyloudnorm"]

    def test_se_reportan_todas(self):
        deps = dependencias()
        for nombre in self.CRITICAS + ["python", "libsndfile"]:
            self.assertIn(nombre, deps)
            self.assertNotEqual(deps[nombre], "desconocida", f"{nombre} sin versión")

    def test_estan_pineadas_en_requirements(self):
        """Sin pinear, dos deploys del mismo commit pueden medir distinto:
        soxr es quien calcula el sobremuestreo del true peak."""
        with open(os.path.join(RAIZ, "requirements.txt"), encoding="utf-8") as f:
            lineas = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        for paquete in self.CRITICAS:
            fijada = [ln for ln in lineas if re.match(rf"^{paquete}==", ln, re.I)]
            self.assertTrue(fijada, f"{paquete} no está pineada con == en requirements.txt")

    def test_las_instaladas_coinciden_con_requirements(self):
        """El entorno que ejecuta los tests debe ser el que declara el repo."""
        with open(os.path.join(RAIZ, "requirements.txt"), encoding="utf-8") as f:
            declaradas = dict(
                ln.strip().split("==", 1) for ln in f
                if "==" in ln and not ln.strip().startswith("#"))
        deps = dependencias()
        desajustes = []
        for paquete in self.CRITICAS:
            esperada = declaradas.get(paquete)
            real = deps.get(paquete)
            if esperada and real and esperada != real:
                desajustes.append(f"{paquete}: requirements {esperada} != instalada {real}")
        self.assertEqual(desajustes, [], "\n".join(desajustes))


class TestVersionesEnElAnalisis(unittest.TestCase):
    def test_el_diagnostico_incluye_las_versiones(self):
        import tempfile

        import numpy as np
        import soundfile as sf
        from engine.diagnostico import generar_diagnostico
        from engine.extractor import extraer_senales

        sr = 44100
        t = np.arange(sr * 10) / sr
        rng = np.random.default_rng(3)
        x = 0.5 * np.sin(2 * np.pi * 55 * t) + 0.2 * rng.standard_normal(len(t))
        x = x / np.max(np.abs(x)) * 0.5
        ruta = os.path.join(tempfile.mkdtemp(), "v.wav")
        sf.write(ruta, np.column_stack([x, x]), sr, subtype="PCM_24")

        r = generar_diagnostico(extraer_senales(ruta, omitir_armonia=True),
                                {"genero": "techno", "fase": "casi_listo",
                                 "objetivo": "sellos", "experiencia": "2-5",
                                 "dificultad_habitual": "mezcla"})
        self.assertIn("versiones", r)
        for campo in ("analysis_engine_version", "peak_algorithm_version",
                      "loudness_algorithm_version"):
            self.assertIn(campo, r["versiones"])

    def test_el_frontend_persiste_las_cinco_versiones(self):
        index = os.path.join(os.path.dirname(RAIZ), "frontend", "index.html")
        with open(index, encoding="utf-8") as f:
            html = f.read()
        bloque = html[html.find("const senales = {"):]
        bloque = bloque[:bloque.find("};")]
        for campo in ("frontend_version", "backend_version",
                      "analysis_engine_version", "peak_algorithm_version",
                      "loudness_algorithm_version"):
            self.assertIn(f"{campo}:", bloque, f"falta {campo} en `senales`")


class TestEndpointTecnico(unittest.TestCase):
    def test_requiere_admin(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi.testclient no disponible")
        os.environ.setdefault("JWT_SECRET", "test")
        os.environ.setdefault("ADMIN_KEY", "test")
        import main
        with TestClient(main.app) as cliente:
            r = cliente.get("/api/tecnico/versiones")
        self.assertEqual(r.status_code, 403,
                         "las versiones exactas de dependencias no son públicas")

    def test_health_sigue_siendo_publico_y_ligero(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi.testclient no disponible")
        os.environ.setdefault("JWT_SECRET", "test")
        os.environ.setdefault("ADMIN_KEY", "test")
        import main
        with TestClient(main.app) as cliente:
            r = cliente.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json()), {"status", "version"},
                         "health lo consulta el chequeo de versión del frontend: "
                         "debe seguir siendo mínimo")


if __name__ == "__main__":
    unittest.main(verbosity=2)
