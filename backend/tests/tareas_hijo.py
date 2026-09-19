"""Tareas de prueba para analisis_proceso. Se ejecutan EN EL PROCESO HIJO
(`python -m analisis_proceso tests.tareas_hijo:<nombre> ...`), nunca aquí."""

import os
import time


def eco(*args, **kwargs):
    """Devuelve lo que recibe más un escalar numpy y el pid del hijo."""
    import numpy as np
    return {"args": list(args), "kwargs": kwargs, "np": np.float64(1.5), "pid": os.getpid()}


def dormir(segundos):
    time.sleep(segundos)
    return "desperté"


def morir(codigo=137):
    """Muere sin escribir resultado, como un proceso matado por falta de memoria."""
    os._exit(codigo)


def sin_senal():
    from engine.extractor import AudioSinSenalAnalizable
    raise AudioSinSenalAnalizable("silencio absoluto", {"pico_dbfs": -120.0})


def no_serializable():
    return lambda: None   # una función local no viaja por pickle
