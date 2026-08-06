"""Guards estáticos sobre frontend/index.html.

LIMITACIÓN CONOCIDA: esto comprueba que el código FUENTE dice lo correcto,
no que el navegador haga lo correcto. La verificación real es manual, con un
análisis de prueba y la fila resultante en Postgres (ver el paso 11 del plan
de fase 1). Aun así estos guards atrapan la clase de regresión que ya se nos
coló una vez: el `0` falsy y un hook sin desestructurar.
"""

import os
import re
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX = os.path.join(RAIZ, "frontend", "index.html")
MAIN = os.path.join(RAIZ, "backend", "main.py")


def _leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


class TestBugFalsy(unittest.TestCase):
    def test_true_peak_no_se_comprueba_por_truthiness(self):
        """`if (tp && ...)` descarta el 0.0 y el -0.0. Ya pasó: ~4-5% de los
        análisis perdieron la línea de true peak del informe."""
        html = _leer(INDEX)
        self.assertNotRegex(
            html, r"true_peak_dbtp\s*&&",
            "true_peak_dbtp comprobado por truthiness: el 0.0 se pierde")
        self.assertNotRegex(
            html, r"sample_peak_dbfs\s*&&",
            "sample_peak_dbfs comprobado por truthiness")

    def test_usa_comparacion_explicita_con_null(self):
        html = _leer(INDEX)
        self.assertIn("_tp != null", html)
        self.assertIn("_sp != null", html)


class TestPersistencia(unittest.TestCase):
    CAMPOS = [
        "true_peak_dbtp", "sample_peak_dbfs", "nivel_true_peak",
        "sample_peak_source", "true_peak_method", "true_peak_oversampling",
        "true_peak_validated", "peak_measurement_sample_rate",
        "peak_measurement_channels",
        "archivo_extension", "archivo_container", "archivo_codec",
        "archivo_subtype", "archivo_sample_format", "archivo_storage_bits",
        "archivo_pcm_bit_depth", "archivo_sample_rate", "archivo_canales",
        "archivo_lossy", "archivo_metadata_source",
        "frontend_version",
    ]

    def test_todos_los_campos_van_en_senales(self):
        html = _leer(INDEX)
        ini = html.find("const senales = {")
        self.assertNotEqual(ini, -1, "no se encuentra el objeto senales")
        bloque = html[ini:html.find("};", ini)]
        for campo in self.CAMPOS:
            self.assertIn(f"{campo}:", bloque, f"falta {campo} en el objeto senales")


class TestValoresCentinelaEnUI(unittest.TestCase):
    def test_existe_el_formateador(self):
        html = _leer(INDEX)
        self.assertIn("function fmtMedida(", html)
        self.assertIn("SENTINELA_SIN_DATO", html)

    def test_los_picos_se_pintan_con_el_formateador(self):
        """Nunca directamente: un análisis viejo pintaría 'undefined'."""
        html = _leer(INDEX)
        self.assertIn("fmtMedida(d.loudness.true_peak_dbtp", html)
        self.assertIn("fmtMedida(d.loudness.sample_peak_dbfs", html)
        self.assertNotIn("{d.loudness.true_peak_dbtp}", html)
        self.assertNotIn("{d.loudness.sample_peak_dbfs}", html)

    def test_el_formateador_cubre_los_cuatro_casos(self):
        html = _leer(INDEX)
        ini = html.find("function fmtMedida(")
        cuerpo = html[ini:ini + 600]
        for caso in ("=== null", "=== undefined", "isFinite", "SENTINELA_SIN_DATO"):
            self.assertIn(caso, cuerpo, f"fmtMedida no contempla {caso}")


class TestHooks(unittest.TestCase):
    def test_todos_los_hooks_usados_estan_desestructurados(self):
        """Regresión de v0.5.69: se usó useMemo sin desestructurarlo y la app
        entera se quedaba en blanco."""
        html = _leer(INDEX)
        m = re.search(r"const\s*\{([^}]*)\}\s*=\s*React;", html)
        self.assertIsNotNone(m, "no se encuentra la desestructuración de React")
        disponibles = {h.strip() for h in m.group(1).split(",") if h.strip()}
        usados = set(re.findall(r"\b(use[A-Z]\w*)\s*\(", html))
        propios = {u for u in usados if u.startswith("useState") is False and False}
        faltan = {u for u in usados - disponibles - propios
                  if u in {"useMemo", "useCallback", "useReducer", "useContext",
                           "useLayoutEffect", "useRef", "useEffect", "useState"}}
        self.assertEqual(faltan, set(), f"hooks usados sin desestructurar: {faltan}")


class TestVersionYCache(unittest.TestCase):
    def test_version_del_frontend_coincide_con_la_del_backend(self):
        html = _leer(INDEX)
        m = re.search(r"const APP_VERSION\s*=\s*'([\d.]+)'", html)
        self.assertIsNotNone(m, "falta APP_VERSION en index.html")
        main = _leer(MAIN)
        m2 = re.search(r'APP_VERSION\s*=\s*"([\d.]+)"', main)
        self.assertIsNotNone(m2, "falta APP_VERSION en main.py")
        self.assertEqual(m.group(1), m2.group(1),
                         "APP_VERSION y /api/health no coinciden: el aviso de "
                         "versión desfasada saltaría siempre")

    def test_la_home_se_sirve_con_no_cache(self):
        """`/` se servía sin Cache-Control y el navegador cacheaba por
        heurística durante semanas."""
        main = _leer(MAIN)
        ini = main.find('@app.get("/")\ndef serve_frontend():')
        self.assertNotEqual(ini, -1, "no se encuentra serve_frontend")
        cuerpo = main[ini:ini + 900]
        self.assertIn("Cache-Control", cuerpo)
        self.assertIn("no-cache", cuerpo)

    def test_hay_comprobacion_de_compatibilidad(self):
        html = _leer(INDEX)
        self.assertIn("comprobarVersionFrontend", html)
        self.assertIn("mt_reload_version", html)

    def test_la_recarga_no_puede_entrar_en_bucle(self):
        html = _leer(INDEX)
        ini = html.find("function comprobarVersionFrontend(")
        cuerpo = html[ini:ini + 1200]
        self.assertIn("sessionStorage.getItem", cuerpo)
        self.assertIn("sessionStorage.setItem", cuerpo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
