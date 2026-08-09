# backend/tests

Batería del motor de picos y loudness. `unittest` de la stdlib: **no añade
ninguna dependencia** a la imagen de producción.

## Ejecutar en local

```bash
cd backend
python -m unittest discover -s tests -t .        # batería completa
python tests/capturar_golden.py                  # ¿cambió algo congelado?
python tests/validar_true_peak.py                # validación contra referencias
python tests/estudio_continua.py                 # estudio de la continua
python tests/reporte_entorno.py                  # todo junto + versiones
```

Necesita las dependencias de `requirements.txt` y `ffmpeg` en el PATH.

## Ejecutar en un entorno equivalente a producción (Docker)

Es la forma correcta de aprobar antes de desplegar: usa el `Dockerfile` real,
con las mismas versiones de Python, libsndfile, soxr y ffmpeg que producción.

```bash
# 1. Construir la imagen real (desde la raíz del repo)
docker build -t mentotrack:test .

# 2. Batería completa dentro de la imagen
docker run --rm -w /app/backend mentotrack:test \
  python -m unittest discover -s tests -t .

# 3. Validación del true peak contra las referencias externas
docker run --rm -w /app/backend mentotrack:test \
  python tests/validar_true_peak.py

# 4. Reporte de versiones + todo lo anterior, en un solo comando.
#    Sale 0 solo si pasan los tests Y la validación.
docker run --rm -w /app/backend mentotrack:test \
  python tests/reporte_entorno.py

# 5. Guardar el reporte como evidencia del deploy
docker run --rm -w /app/backend mentotrack:test \
  python tests/reporte_entorno.py > reporte-$(git rev-parse --short HEAD).txt
```

Los tests que tocan Postgres no existen: la batería es toda offline y no
necesita `DATABASE_URL` ni red.

## Propuesta de CI (NO aplicada)

En el repo no hay `.github/workflows/`. Este job sería el equivalente
automático de los comandos de arriba. **No lo he creado**: tocar la
configuración de despliegue necesita tu visto bueno.

```yaml
# .github/workflows/motor.yml  — PROPUESTA, no está en el repo
name: motor
on:
  pull_request:
    paths: ['backend/engine/**', 'backend/tests/**', 'backend/requirements.txt',
            'frontend/index.html', 'Dockerfile']
  push:
    branches: [main]

jobs:
  tests-en-imagen-real:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Construir la imagen de producción
        run: docker build -t mentotrack:ci .
      - name: Reporte de entorno + batería + validación
        run: |
          docker run --rm -w /app/backend mentotrack:ci \
            python tests/reporte_entorno.py | tee reporte.txt
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: reporte-motor
          path: reporte.txt
```

Ojo con una cosa si se activa: `push: [main]` es la rama que dispara el
deploy de Railway. El job **no** bloquea ese deploy — Railway y GitHub
Actions corren en paralelo. Para que bloquease de verdad haría falta una
protección de rama que exija el check en verde antes del merge, y eso ya es
cambiar la configuración del repositorio.

## Qué hay aquí

| Fichero | Para qué |
|---|---|
| `fixtures.py` | 25 archivos de audio deterministas. Semilla fija: mismos bytes en cada ejecución |
| `golden_loudness.json` | Comportamiento congelado ANTES de v0.5.71. No regenerar a la ligera |
| `capturar_golden.py` | Compara contra el golden. Los cambios aprobados se declaran uno a uno en `CAMBIOS_AUTORIZADOS` |
| `itu_bs1770.py` | FIR 4× de referencia del anexo 2 de BS.1770-5. **Solo tests**, no es el de producción |
| `reconstruccion_exacta.py` | La verdad, no otra implementación: interpolación sinc exacta. Es el árbitro cuando los medidores discrepan. **Solo tests** |
| `validar_true_peak.py` | Contrasta contra valor analítico, ffmpeg, sinc por FFT y polifásico de scipy |
| `estudio_continua.py` | Compara los cuatro métodos sobre señales con discontinuidad |
| `reporte_entorno.py` | Versiones + toda la batería en un comando |
| `test_picos.py` | Contrato de los campos de picos, precisión, fallback, clasificación congelada |
| `test_formato.py` | Metadatos del archivo; separación storage_bits / pcm_bit_depth |
| `test_sin_senal.py` | 422 en silencio; un archivo bajo pero real se analiza igual |
| `test_itu_referencia.py` | soxr contra el FIR normativo |
| `test_reconstruccion.py` | Qué mide de verdad cada medidor. Verifica la referencia exacta y acota el error de cada candidato |
| `test_recorte.py` | Fase 2B: contar muestras a fondo de escala. Qué se puede afirmar, qué no se acusa y que el texto enseñe |
| `test_versiones.py` | Versionado de algoritmos y dependencias fijadas |
| `test_frontend.py` | Guards estáticos sobre `index.html` |

## Notas

`test_frontend.py` comprueba el código FUENTE, no el navegador. La
verificación real es manual: un análisis de prueba y mirar la fila en
Postgres.

El invariante `true_peak >= sample_peak` está forzado por un `max()` en el
código: sirve como red de seguridad, **no** valida el algoritmo. Lo que valida
el algoritmo es `validar_true_peak.py`.
