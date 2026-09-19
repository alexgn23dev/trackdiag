"""Excepciones del motor que el servidor necesita reconocer sin cargar el
extractor.

El análisis corre en un proceso hijo (ver analisis_proceso.py) y sus
excepciones vuelven al servidor por pickle: para reconstruirlas, el servidor
importa el módulo donde está definida la clase. Si viviera en
engine.extractor, capturar un error arrastraría librosa, numba y scipy al
proceso del servidor (unos 200 MB que no se devuelven). Por eso vive aquí, sin
dependencias, y engine.extractor la reexporta.
"""


class AudioSinSenalAnalizable(Exception):
    """El archivo se decodifica pero no contiene señal que se pueda analizar.

    Silencio digital, un archivo de puros ceros o muestras no finitas. NO se
    lanza por tener nivel bajo: para eso está el nivel "muy_bajo" del
    diagnóstico normal.
    """

    codigo = "AUDIO_WITHOUT_ANALYZABLE_SIGNAL"

    def __init__(self, motivo: str, detalle: dict | None = None):
        super().__init__(motivo)
        self.motivo = motivo
        self.detalle = detalle or {}
