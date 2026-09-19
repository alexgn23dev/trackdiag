"""El proceso del servidor no carga librosa.

librosa arrastra numba, llvmlite y scipy: unos 200 MB que, una vez cargados,
el servidor ya no devuelve. El análisis corre en un proceso hijo
(analisis_proceso), así que al servidor solo le quedaban dos motivos para
importarla: medir la duración de los uploads y reconocer la excepción
AudioSinSenalAnalizable. La duración se mide ahora con `_duracion_audio`
(soundfile y, si no puede, audioread: lo mismo que hace librosa por dentro) y
la excepción vive en engine/excepciones.py, sin dependencias.

El test de contrato arranca el servidor en un proceso limpio, lo recorre por
todos los caminos que antes cargaban librosa y mira qué módulos quedaron.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

PESADOS = ("librosa", "numba", "llvmlite", "scipy", "pyloudnorm", "soxr", "sklearn")

# Se ejecuta en un proceso aparte: el de los tests ya tiene librosa cargada.
_SERVIDOR = r'''
import json, os, sys
sys.path.insert(0, os.getcwd())
import main
from fastapi.testclient import TestClient
main._admin_email_from_cookie = lambda request: "admin@prueba"
track, silencio, corto = sys.argv[1:4]
datos = {"genero": "techno", "fase": "casi_listo", "objetivo": "sellos",
         "experiencia": "2-5", "dificultad_habitual": "mezcla"}
res = {}
def diagnostico(ruta):
    with open(ruta, "rb") as fh:
        return c.post("/api/diagnostico", files={"audio": ("track.wav", fh, "audio/wav")}, data=datos)
with TestClient(main.app) as c:
    r = diagnostico(track); res["diagnostico"] = r.status_code
    res["tiene_datos_audio"] = "datos_audio" in r.json()
    r = diagnostico(silencio); res["silencio"] = [r.status_code, r.json().get("codigo")]
    r = diagnostico(corto); res["corto"] = r.status_code
    with open(track, "rb") as fh:
        r = c.post("/api/internal/features", files={"audio": ("track.wav", fh, "audio/wav")},
                   headers={"X-Relesit-Secret": "secreto-de-prueba-con-32-caracteres-o-mas"})
    res["features"] = r.status_code
    r = c.get("/api/tecnico/versiones")
    res["versiones"] = [r.status_code, r.json().get("validacion_true_peak")]
res["modulos"] = sorted(m for m in %r if m in sys.modules)
print("RESULTADO " + json.dumps(res))
''' % (PESADOS,)


def _escribir_audios(carpeta):
    import numpy as np
    import soundfile as sf
    sr = 44100
    t = np.arange(int(sr * 12.0)) / sr
    fase = (t * 128 / 60) % 1.0
    x = 0.6 * np.sin(2 * np.pi * (50 + 90 * np.exp(-fase * 30)) * t) * np.exp(-fase * 9)
    x += 0.05 * np.random.default_rng(5).standard_normal(len(t))
    rutas = {}
    for nombre, senal in (("track", x), ("silencio", np.zeros(int(sr * 10.0))), ("corto", x[: sr * 3])):
        rutas[nombre] = os.path.join(carpeta, nombre + ".wav")
        sf.write(rutas[nombre], np.stack([senal, senal], axis=1), sr, subtype="PCM_24")
    return rutas


class TestElServidorNoCargaLibrosa(unittest.TestCase):

    def test_ningun_camino_carga_librosa(self):
        try:
            import fastapi.testclient  # noqa: F401
        except ImportError:
            self.skipTest("fastapi.testclient no disponible")
        carpeta = tempfile.mkdtemp(prefix="mentotrack_sin_librosa_")
        try:
            rutas = _escribir_audios(carpeta)
            # SSO_SECRET de 32+ caracteres: con menos, main.py apaga el puente con Relesit.
            env = dict(os.environ, JWT_SECRET="test", ADMIN_KEY="test",
                       SSO_SECRET="secreto-de-prueba-con-32-caracteres-o-mas",
                       SESIONES_PATH=os.path.join(carpeta, "sesiones.jsonl"))
            p = subprocess.run([sys.executable, "-c", _SERVIDOR, rutas["track"], rutas["silencio"], rutas["corto"]],
                               cwd=BACKEND, env=env, capture_output=True, text=True, timeout=600)
        finally:
            shutil.rmtree(carpeta, ignore_errors=True)
        linea = [l for l in p.stdout.splitlines() if l.startswith("RESULTADO ")]
        self.assertTrue(linea, "el servidor de prueba no terminó:\n" + p.stdout[-2000:] + p.stderr[-2000:])
        res = json.loads(linea[-1][len("RESULTADO "):])

        # Los caminos siguen funcionando igual...
        self.assertEqual(res["diagnostico"], 200)
        self.assertTrue(res["tiene_datos_audio"])
        self.assertEqual(res["silencio"], [422, "AUDIO_WITHOUT_ANALYZABLE_SIGNAL"],
                         "la excepción del hijo tiene que llegar con su clase")
        self.assertEqual(res["corto"], 400, "la duración mínima se sigue comprobando")
        self.assertEqual(res["features"], 200)
        self.assertEqual(res["versiones"][0], 200)
        self.assertEqual(set(res["versiones"][1]), {
            "true_peak_ground_truth_validation_passed", "true_peak_internal_validation_passed",
            "true_peak_external_validation_passed", "true_peak_validated"})
        # ...y ninguno ha cargado librosa ni lo que arrastra.
        self.assertEqual(res["modulos"], [], "el proceso del servidor cargó librerías de análisis")

    def test_main_no_importa_el_extractor_ni_librosa(self):
        with open(os.path.join(BACKEND, "main.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("import librosa", src)
        self.assertNotIn("from engine.extractor import", src)
        self.assertNotIn("from engine import extractor", src)

    def test_la_excepcion_no_depende_del_extractor(self):
        with open(os.path.join(BACKEND, "engine", "excepciones.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("import", src.split('"""', 2)[-1], "engine/excepciones.py no puede importar nada")
        from engine.excepciones import AudioSinSenalAnalizable
        from engine.extractor import AudioSinSenalAnalizable as reexportada
        self.assertIs(AudioSinSenalAnalizable, reexportada)


class TestDuracionIgualQueLibrosa(unittest.TestCase):
    """`_duracion_audio` sustituye a librosa.get_duration(path=...): tiene que
    dar exactamente lo mismo, porque decide el mínimo de 8 s y el máximo de
    20 min."""

    @classmethod
    def setUpClass(cls):
        try:
            import numpy as np
            import soundfile as sf
        except ImportError:
            raise unittest.SkipTest("numpy/soundfile no disponibles")
        cls.carpeta = tempfile.mkdtemp(prefix="mentotrack_duracion_")
        sr = 44100
        x = 0.1 * np.random.default_rng(9).standard_normal((int(sr * 9.5), 2))
        cls.rutas = {}
        for ext, kw in ((".wav", {"subtype": "PCM_24"}), (".flac", {}),
                        (".ogg", {"subtype": "VORBIS"}), (".aiff", {"subtype": "PCM_16"})):
            cls.rutas[ext] = os.path.join(cls.carpeta, "x" + ext)
            sf.write(cls.rutas[ext], x, sr, **kw)
        if shutil.which("ffmpeg"):
            mp3 = os.path.join(cls.carpeta, "x.mp3")
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", cls.rutas[".wav"],
                                "-codec:a", "libmp3lame", "-b:a", "192k", mp3])
            if r.returncode == 0:
                cls.rutas[".mp3"] = mp3

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.carpeta, ignore_errors=True)

    def test_misma_duracion_en_todos_los_formatos(self):
        import librosa
        import main
        for ext, ruta in self.rutas.items():
            with self.subTest(formato=ext):
                self.assertEqual(main._duracion_audio(ruta), librosa.get_duration(path=ruta))

    def test_si_soundfile_no_puede_usa_audioread_como_librosa(self):
        from unittest import mock

        import librosa
        import main
        import soundfile as sf

        def falla(*args, **kwargs):
            raise sf.SoundFileRuntimeError("simulado")

        ruta = self.rutas[".wav"]
        with mock.patch.object(sf, "info", falla), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            esperado = librosa.get_duration(path=ruta)
            self.assertEqual(main._duracion_audio(ruta), esperado)
        self.assertAlmostEqual(esperado, 9.5, places=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
