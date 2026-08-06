"""Aislamiento del entorno preview y estados de validación del true peak.

Lo que se protege: un preview que herede DATABASE_URL, RESEND_API_KEY o
JWT_SECRET de producción escribiría en la base real, mandaría correos a
usuarios reales y emitiría tokens válidos en producción. La app debe negarse
a arrancar antes que hacer eso.
"""

import importlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


CLAVES = ["MENTOTRACK_ENV", "DATABASE_URL", "PROD_DB_FINGERPRINT",
          "RESEND_API_KEY", "PROD_RESEND_FINGERPRINT", "JWT_SECRET",
          "PROD_JWT_FINGERPRINT", "SHEETS_ACTIVO", "EMAIL_ACTIVO",
          "WEBHOOKS_ACTIVOS", "ANALITICA_ACTIVA", "PREVIEW_ALLOW_UNSAFE",
          "SHEETS_WEBHOOK", "PREVIEW_DB_INTERNA_OK"]


class BaseEntorno(unittest.TestCase):
    """Aísla os.environ por test.

    Las variables tienen que seguir puestas MIENTRAS corre el test, no solo
    durante el reload: `comprobar_aislamiento()` lee os.environ en cada
    llamada. Por eso se restauran en tearDown y no dentro de `_recargar`.
    """

    def setUp(self):
        self._previas = {k: os.environ.get(k) for k in CLAVES}

    def tearDown(self):
        for k, v in self._previas.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        self._recargar()   # deja el módulo como el proceso real

    def _recargar(self, **variables):
        for k in CLAVES:
            os.environ.pop(k, None)
        for k, v in variables.items():
            if v is not None:
                os.environ[k] = v
        import entorno
        return importlib.reload(entorno)


class TestHuellas(BaseEntorno):
    def test_no_permite_recuperar_el_secreto(self):
        mod = self._recargar()
        secreto = "postgresql://usuario:contrasena@host:5432/base"
        h = mod.huella(secreto)
        self.assertEqual(len(h), 16)
        self.assertNotIn("contrasena", h)
        self.assertNotIn("usuario", h)

    def test_es_determinista_y_distingue(self):
        mod = self._recargar()
        self.assertEqual(mod.huella("a"), mod.huella("a"))
        self.assertNotEqual(mod.huella("a"), mod.huella("b"))

    def test_valor_vacio(self):
        self.assertEqual(self._recargar().huella(""), "")


class TestDeteccionDeProduccion(BaseEntorno):
    URL_PROD = "postgresql://u:p@postgres.railway.internal:5432/railway"
    URL_PREVIEW = "postgresql://u2:p2@preview.proxy.rlwy.net:41234/preview"

    def test_preview_con_la_misma_url_que_produccion_no_arranca(self):
        mod = self._recargar()
        fp = mod.huella(self.URL_PROD)
        mod = self._recargar(MENTOTRACK_ENV="preview", DATABASE_URL=self.URL_PROD,
                        PROD_DB_FINGERPRINT=fp)
        with self.assertRaises(mod.ConfiguracionInsegura):
            mod.proteger_arranque()

    def test_preview_con_la_misma_base_pero_otra_credencial_tampoco(self):
        """Cambiar la contraseña no cambia la base de datos."""
        mod = self._recargar()
        fp_identidad = mod.huella(mod._identidad_db(self.URL_PROD))
        otra_credencial = "postgresql://otro:otra@postgres.railway.internal:5432/railway"
        mod = self._recargar(MENTOTRACK_ENV="preview", DATABASE_URL=otra_credencial,
                        PROD_DB_FINGERPRINT=fp_identidad)
        problemas = mod.comprobar_aislamiento()
        self.assertTrue(any("host/puerto/base" in p for p in problemas), problemas)

    def test_preview_con_base_propia_arranca(self):
        mod = self._recargar()
        fp = mod.huella(self.URL_PROD)
        mod = self._recargar(MENTOTRACK_ENV="preview", DATABASE_URL=self.URL_PREVIEW,
                        PROD_DB_FINGERPRINT=fp)
        mod.proteger_arranque()   # no debe lanzar
        self.assertEqual(mod.comprobar_aislamiento(), [])

    def test_preview_sin_huella_de_referencia_avisa(self):
        """Sin PROD_DB_FINGERPRINT no se puede comprobar nada: no se calla."""
        mod = self._recargar(MENTOTRACK_ENV="preview", DATABASE_URL=self.URL_PREVIEW)
        self.assertTrue(any("PROD_DB_FINGERPRINT" in p
                            for p in mod.comprobar_aislamiento()))

    def test_host_interno_de_railway_es_sospechoso(self):
        mod = self._recargar(MENTOTRACK_ENV="preview", DATABASE_URL=self.URL_PROD,
                        PROD_DB_FINGERPRINT="otracosa")
        self.assertTrue(any("host interno de Railway" in p
                            for p in mod.comprobar_aislamiento()))

    def test_resend_de_produccion(self):
        mod = self._recargar()
        fp = mod.huella("re_clave_de_produccion")
        mod = self._recargar(MENTOTRACK_ENV="preview", RESEND_API_KEY="re_clave_de_produccion",
                        PROD_RESEND_FINGERPRINT=fp, DATABASE_URL=self.URL_PREVIEW,
                        PROD_DB_FINGERPRINT="x")
        self.assertTrue(any("RESEND_API_KEY es la de producción" in p
                            for p in mod.comprobar_aislamiento()))

    def test_jwt_de_produccion(self):
        mod = self._recargar()
        fp = mod.huella("secreto_jwt_de_produccion")
        mod = self._recargar(MENTOTRACK_ENV="preview", JWT_SECRET="secreto_jwt_de_produccion",
                        PROD_JWT_FINGERPRINT=fp, DATABASE_URL=self.URL_PREVIEW,
                        PROD_DB_FINGERPRINT="x")
        self.assertTrue(any("JWT_SECRET es el de producción" in p
                            for p in mod.comprobar_aislamiento()))

    def test_produccion_no_se_comprueba_a_si_misma(self):
        mod = self._recargar(MENTOTRACK_ENV="production", DATABASE_URL=self.URL_PROD)
        self.assertEqual(mod.comprobar_aislamiento(), [])
        mod.proteger_arranque()

    def test_romper_el_cristal(self):
        mod = self._recargar()
        fp = mod.huella(self.URL_PROD)
        mod = self._recargar(MENTOTRACK_ENV="preview", DATABASE_URL=self.URL_PROD,
                        PROD_DB_FINGERPRINT=fp, PREVIEW_ALLOW_UNSAFE="1")
        mod.proteger_arranque()   # avisa pero deja arrancar


class TestServiciosExternos(BaseEntorno):
    def test_en_preview_todo_lo_externo_viene_apagado(self):
        mod = self._recargar(MENTOTRACK_ENV="preview")
        self.assertFalse(mod.SHEETS_ACTIVO)
        self.assertFalse(mod.EMAIL_ACTIVO)
        self.assertFalse(mod.WEBHOOKS_ACTIVOS)
        self.assertFalse(mod.ANALITICA_ACTIVA)

    def test_en_produccion_todo_viene_encendido(self):
        mod = self._recargar(MENTOTRACK_ENV="production")
        self.assertTrue(mod.SHEETS_ACTIVO)
        self.assertTrue(mod.EMAIL_ACTIVO)
        self.assertTrue(mod.WEBHOOKS_ACTIVOS)

    def test_encender_el_email_en_preview_se_marca_como_problema(self):
        mod = self._recargar(MENTOTRACK_ENV="preview", EMAIL_ACTIVO="1",
                        RESEND_API_KEY="re_x", DATABASE_URL="postgresql://a:b@c:1/d",
                        PROD_DB_FINGERPRINT="x")
        self.assertTrue(any("se enviarían correos de verdad" in p
                            for p in mod.comprobar_aislamiento()))


class TestResumen(BaseEntorno):
    def test_no_expone_secretos(self):
        mod = self._recargar(MENTOTRACK_ENV="preview",
                        DATABASE_URL="postgresql://usuario:secreto@h:5432/b",
                        JWT_SECRET="jwt_secreto", PROD_DB_FINGERPRINT="x")
        texto = repr(mod.resumen())
        for secreto in ("secreto", "usuario", "jwt_secreto"):
            self.assertNotIn(secreto, texto, f"{secreto} filtrado en el resumen")

    def test_incluye_lo_necesario(self):
        mod = self._recargar(MENTOTRACK_ENV="preview", DATABASE_URL="postgresql://a:b@c:1/d",
                        PROD_DB_FINGERPRINT="x")
        r = mod.resumen()
        self.assertEqual(r["entorno"], "preview")
        self.assertTrue(r["es_preview"])
        self.assertIn("servicios", r)
        self.assertIn("aislamiento_ok", r)


class TestEstadosDeValidacion(BaseEntorno):
    """Los tres estados no pueden colapsarse en uno."""

    def test_son_tres_campos_distintos(self):
        from engine import extractor
        self.assertIsInstance(extractor.TRUE_PEAK_INTERNAL_VALIDATION_PASSED, bool)
        self.assertIsInstance(extractor.TRUE_PEAK_EXTERNAL_VALIDATION_PASSED, bool)
        self.assertIsInstance(extractor._TRUE_PEAK_VALIDATED, bool)

    def test_interna_pasa(self):
        from engine import extractor
        self.assertTrue(extractor.TRUE_PEAK_INTERNAL_VALIDATION_PASSED,
                        "la batería automatizada pasa: ver RESULTADOS_VALIDACION.md")

    def test_externa_no_pasa_todavia(self):
        from engine import extractor
        self.assertFalse(extractor.TRUE_PEAK_EXTERNAL_VALIDATION_PASSED,
                         "falta el contraste manual con un medidor profesional")

    def test_la_global_es_la_conjuncion_y_no_se_pone_a_mano(self):
        from engine import extractor
        self.assertEqual(
            extractor._TRUE_PEAK_VALIDATED,
            extractor.TRUE_PEAK_INTERNAL_VALIDATION_PASSED
            and extractor.TRUE_PEAK_EXTERNAL_VALIDATION_PASSED)
        self.assertFalse(extractor._TRUE_PEAK_VALIDATED,
                         "sin validación externa, la global no puede ser True")

    def test_la_global_se_deriva_en_el_codigo(self):
        """Debe ser una expresión, no un literal: así no se puede poner a True
        sin tocar los dos estados de los que depende."""
        ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "engine", "extractor.py")
        with open(ruta, encoding="utf-8") as f:
            codigo = f.read()
        self.assertIn("_TRUE_PEAK_VALIDATED = (TRUE_PEAK_INTERNAL_VALIDATION_PASSED", codigo)

    def test_llegan_al_analisis(self):
        import tempfile

        import numpy as np
        import soundfile as sf
        from engine.extractor import extraer_senales
        from tests import fixtures as fx
        # Material con pulso: un seno puro hace que beat_track devuelva 0 BPM
        # y el extractor divide entre el tempo (ver NOTA en la entrega).
        rng = np.random.default_rng(fx.SEED)
        x = fx._escalar_a_sample_peak(fx._musical(44100, 10.0, rng), -1.0)
        ruta = os.path.join(tempfile.mkdtemp(), "e.wav")
        sf.write(ruta, np.column_stack([x, x]), 44100, subtype="PCM_24")
        lo = extraer_senales(ruta, omitir_armonia=True)["loudness"]
        for campo in ("true_peak_internal_validation_passed",
                      "true_peak_external_validation_passed", "true_peak_validated"):
            self.assertIn(campo, lo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
