"""Salida controlada para archivos sin señal analizable.

El caso que motivó esto: pyloudnorm devuelve -inf con silencio absoluto, ese
-inf llegaba a la respuesta y Starlette (allow_nan=False) respondía 500 con
`Out of range float values are not JSON compliant`. Ahora es un 422 con
código estable y sin generar diagnóstico.

Lo importante de estos tests no es solo que el silencio se rechace, sino que
un archivo BAJO PERO REAL se siga analizando con normalidad.
"""

import json
import math
import os
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.extractor import (  # noqa: E402
    AudioSinSenalAnalizable, _comprobar_senal_analizable, extraer_senales,
)

_DIR = tempfile.mkdtemp(prefix="mentotrack_sinsenal_")
SR = 44100
DUR = 10.0   # por encima del mínimo de 8 s del endpoint


def _escribir(nombre, x, subtype="PCM_24"):
    ruta = os.path.join(_DIR, nombre)
    sf.write(ruta, x, SR, subtype=subtype)
    return ruta


def _db_a_lin(db):
    return 10.0 ** (db / 20.0)


def _musical(pico_db, n=None, canales=1):
    n = n or int(SR * DUR)
    rng = np.random.default_rng(7)
    t = np.arange(n) / SR
    x = 0.6 * np.sin(2 * np.pi * 55 * t) + 0.3 * rng.standard_normal(n)
    x = x / np.max(np.abs(x)) * _db_a_lin(pico_db)
    return x if canales == 1 else np.column_stack([x] * canales)


class TestRechazo(unittest.TestCase):

    def test_silencio_digital_exacto(self):
        with self.assertRaises(AudioSinSenalAnalizable) as ctx:
            _comprobar_senal_analizable(np.zeros(int(SR * DUR)))
        self.assertEqual(ctx.exception.detalle["motivo_tecnico"], "silencio")

    def test_silencio_estereo(self):
        ruta = _escribir("silencio_estereo.wav", np.zeros((int(SR * DUR), 2)))
        with self.assertRaises(AudioSinSenalAnalizable):
            extraer_senales(ruta)

    def test_silencio_mono(self):
        ruta = _escribir("silencio_mono.wav", np.zeros(int(SR * DUR)))
        with self.assertRaises(AudioSinSenalAnalizable):
            extraer_senales(ruta)

    def test_ruido_por_debajo_del_umbral(self):
        """-100 dBFS de pico: por debajo del umbral, no hay nada que analizar."""
        x = _musical(-100.0)
        with self.assertRaises(AudioSinSenalAnalizable):
            _comprobar_senal_analizable(x)

    def test_array_vacio(self):
        with self.assertRaises(AudioSinSenalAnalizable) as ctx:
            _comprobar_senal_analizable(np.zeros(0))
        self.assertEqual(ctx.exception.detalle["motivo_tecnico"], "sin_muestras")

    def test_todo_no_finito(self):
        x = np.full(1000, np.nan)
        with self.assertRaises(AudioSinSenalAnalizable) as ctx:
            _comprobar_senal_analizable(x)
        self.assertEqual(ctx.exception.detalle["motivo_tecnico"], "muestras_no_finitas")

    def test_codigo_estable(self):
        self.assertEqual(AudioSinSenalAnalizable.codigo,
                         "AUDIO_WITHOUT_ANALYZABLE_SIGNAL")

    def test_detalle_serializable(self):
        try:
            _comprobar_senal_analizable(np.zeros(1000))
        except AudioSinSenalAnalizable as e:
            json.dumps(e.detalle, allow_nan=False)   # no debe lanzar
        else:
            self.fail("debería haber lanzado")


class TestNoRechazo(unittest.TestCase):
    """Un archivo bajo NO es un archivo sin señal."""

    def test_muy_bajo_pero_no_silencioso_pasa(self):
        # -60 dBFS de pico: bajísimo para música, pero es señal real.
        _comprobar_senal_analizable(_musical(-60.0))

    def test_bounce_sin_masterizar_pasa(self):
        _comprobar_senal_analizable(_musical(-30.0))

    def test_archivo_bajo_se_analiza_entero(self):
        ruta = _escribir("bajo_pero_real.wav", _musical(-45.0, canales=2))
        s = extraer_senales(ruta, omitir_armonia=True)
        self.assertIn("loudness", s)
        self.assertTrue(math.isfinite(s["loudness"]["lufs_integrado"]))
        self.assertEqual(s["loudness"]["nivel"], "muy_bajo",
                         "un archivo muy bajo debe diagnosticarse, no rechazarse")

    def test_unas_pocas_muestras_no_finitas_no_bloquean(self):
        x = _musical(-12.0)
        x[10] = np.nan
        x[20] = np.inf
        _comprobar_senal_analizable(x)   # no debe lanzar


class TestSinInfinitosEnLaRespuesta(unittest.TestCase):

    def test_ningun_valor_no_finito_en_un_analisis_real(self):
        ruta = _escribir("normal.wav", _musical(-1.0, canales=2))
        s = extraer_senales(ruta, omitir_armonia=True)

        def revisar(obj, camino=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    revisar(v, f"{camino}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    revisar(v, f"{camino}[{i}]")
            elif isinstance(obj, float):
                self.assertTrue(math.isfinite(obj), f"valor no finito en {camino}: {obj}")

        revisar(s)

    def test_respuesta_serializable_por_starlette(self):
        """Reproduce el 500: Starlette usa allow_nan=False."""
        from starlette.responses import JSONResponse
        ruta = _escribir("normal2.wav", _musical(-1.0, canales=2))
        s = extraer_senales(ruta, omitir_armonia=True)
        JSONResponse(s["loudness"]).render(s["loudness"])   # no debe lanzar

    def test_inf_seguiria_rompiendo_starlette(self):
        """Documenta por qué existe la guarda: sin ella, esto es un 500."""
        from starlette.responses import JSONResponse
        with self.assertRaises(ValueError):
            JSONResponse({"lufs": float("-inf")}).render({"lufs": float("-inf")})


class TestEndpointDevuelve422(unittest.TestCase):
    """El endpoint responde 422 con el código estable y sin diagnóstico."""

    def test_endpoint(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi.testclient no disponible")
        os.environ.setdefault("JWT_SECRET", "test")
        os.environ.setdefault("ADMIN_KEY", "test")
        import main
        ruta = _escribir("silencio_endpoint.wav", np.zeros((int(SR * DUR), 2)))
        with TestClient(main.app) as cliente, open(ruta, "rb") as fh:
            r = cliente.post("/api/diagnostico", files={"audio": ("silencio.wav", fh, "audio/wav")},
                             data={"genero": "techno", "fase": "casi_listo",
                                   "objetivo": "sellos", "experiencia": "2-5",
                                   "dificultad_habitual": "mezcla"})
        self.assertEqual(r.status_code, 422, r.text)
        cuerpo = r.json()
        self.assertEqual(cuerpo["codigo"], "AUDIO_WITHOUT_ANALYZABLE_SIGNAL")
        self.assertIn("error", cuerpo)
        self.assertNotIn("datos_audio", cuerpo, "no debe generarse diagnóstico")
        self.assertNotIn("Infinity", r.text)
        self.assertNotIn("NaN", r.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
