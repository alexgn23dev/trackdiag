# Mentotrack — Documentación técnica completa

Última actualización: 24 abril 2026 | Versión: 0.4.1

---

## 1. Qué es Mentotrack

Mentotrack es una app web de diagnóstico y orientación para productores de música electrónica. El usuario sube un bounce de su track, responde un cuestionario de contexto, y recibe un diagnóstico priorizado que le dice qué corregir primero y qué no tocar todavía.

No es una herramienta de análisis de audio. Es un sistema de triage pedagógico que combina señales de audio con contexto del usuario para producir un diagnóstico accionable.

El valor real está en tres cosas: reducir la niebla (el usuario llega confundido y se va con un diagnóstico claro), reordenar prioridades (el usuario cree que su problema es X, el sistema le muestra que es Y), y dar permiso para no hacer ciertas cosas todavía.

**Dominio:** www.mentotrack.com
**Marca:** Producción Online
**Audiencia:** Productores principiantes/intermedios de house, techno, trance y subgéneros


---

## 2. Stack técnico

### Frontend
- Single-file React+Tailwind SPA (`frontend/index.html`, ~119KB)
- Dashboard admin separado (`frontend/dashboard.html`, ~65KB)
- Tipografía custom: Termina Demi (woff/woff2) para títulos, Arimo (Google Fonts) para cuerpo
- Logo SVG: wordmark "mentotrack" con knob/onda verde integrada

### Backend
- Python 3.11 + FastAPI v0.115
- Motor de análisis: librosa 0.11 + pyloudnorm + scipy + numpy
- Auth: bcrypt (contraseñas) + PyJWT (tokens de sesión)
- Rate limiting: slowapi
- Proxy a Google Sheets: httpx (todo vía POST)

### Infraestructura
- **Hosting:** Railway (auto-deploy desde GitHub)
- **DNS:** Cloudflare (nameservers: blair.ns.cloudflare.com, jack.ns.cloudflare.com)
- **Dominio:** mentotrack.com (comprado en Hostinger, DNS delegado a Cloudflare)
- **Base de datos:** Google Sheets vía Apps Script (pestaña principal = diagnósticos, pestaña "usuarios" = auth)
- **Repo:** GitHub (privado)

### Docker
```dockerfile
FROM python:3.11-slim
# libsndfile1 + ffmpeg para procesamiento de audio
# uvicorn main:app --host 0.0.0.0 --port ${PORT}
```


---

## 3. Arquitectura del sistema

```
┌─────────────────────────────────────────────────────┐
│              FRONTEND (SPA React+Tailwind)           │
│  Landing → Upload → Cuestionario → Diagnóstico →    │
│  Feedback → Panel usuario (historial)               │
└──────────┬──────────────────────────────────────────┘
           │ POST /api/*
           ▼
┌─────────────────────────────────────────────────────┐
│              BACKEND (FastAPI + librosa)             │
│                                                     │
│  ┌──────────────┐   ┌───────────────────────────┐  │
│  │  extractor.py │──▶│  reglas.py + templates.py  │  │
│  │  (señales     │   │  (motor de diagnóstico)    │  │
│  │  de audio)    │   │                            │  │
│  └──────────────┘   └───────────────────────────┘  │
│         │                        │                  │
│  ┌──────────────┐   ┌───────────────────────────┐  │
│  │ diagnostico  │   │  contextualizador.py       │  │
│  │ .py (orquesta│   │  (feedback didáctico por   │  │
│  │ dor)         │   │   parámetro y género)      │  │
│  └──────────────┘   └───────────────────────────┘  │
│         │                                           │
│    ┌────────────────────────────────────────┐       │
│    │  Proxy Google Sheets (POST)            │       │
│    │  Auth (bcrypt + JWT)                   │       │
│    │  Rate limiting (slowapi)               │       │
│    └────────────────────────────────────────┘       │
└──────────┬──────────────────────────────────────────┘
           │ POST (JSON body)
           ▼
┌─────────────────────────────────────────────────────┐
│        GOOGLE APPS SCRIPT (v2, POST-only)           │
│  Pestaña 1: diagnósticos (timestamp, email,         │
│    proyecto, formulario, diagnóstico, señales,      │
│    fue_util, comentario, feedback_real)              │
│  Pestaña "usuarios": email, password_hash,          │
│    fecha_registro                                   │
└─────────────────────────────────────────────────────┘
```


---

## 4. Estructura de archivos

```
trackdiag/
├── Dockerfile
├── .gitignore
├── apps_script.js          # Código del Apps Script (referencia, se pega en Google)
├── arquitectura.svg        # Diagrama visual de arquitectura
├── MENTOTRACK.md           # Este documento
├── backend/
│   ├── main.py             # FastAPI app (605 líneas, v0.4.0)
│   ├── requirements.txt    # 11 dependencias
│   ├── sesiones.jsonl      # Log local de sesiones de diagnóstico
│   └── engine/
│       ├── __init__.py
│       ├── extractor.py    # Extracción de señales de audio (~50 data points)
│       ├── reglas.py       # Motor de reglas ponderadas (9 diagnósticos)
│       ├── diagnostico.py  # Orquestador: señales + contexto → diagnóstico
│       ├── contextualizador.py  # Feedback didáctico contextualizado por género
│       └── templates.py    # Templates de texto para cada diagnóstico
└── frontend/
    ├── index.html          # SPA principal (~119KB)
    ├── dashboard.html      # Dashboard admin (~65KB)
    ├── logo.svg            # Wordmark Mentotrack
    ├── Termina-Demi.woff
    └── Termina-Demi.woff2
```


---

## 5. Endpoints de la API

### Públicos (sin auth)
| Método | Ruta | Rate limit | Descripción |
|--------|------|------------|-------------|
| GET | `/` | — | Sirve el SPA (index.html) |
| GET | `/api/health` | — | Health check, devuelve versión |
| GET | `/api/opciones` | — | Opciones del cuestionario (géneros, fases, etc.) |
| POST | `/api/diagnostico` | 3/min | Recibe audio + contexto, devuelve diagnóstico |
| POST | `/api/auth/acceder` | 5/min | Login/registro unificado (email + contraseña) |

### Con JWT (Authorization: Bearer)
| Método | Ruta | Rate limit | Descripción |
|--------|------|------------|-------------|
| POST | `/api/auth/historial` | 10/min | Refresca historial del usuario |
| POST | `/api/feedback` | 10/min | Guarda feedback de utilidad |
| POST | `/api/feedback-request` | 5/min | Guarda solicitud de track review |

### Proxy a Google Sheets
| Método | Ruta | Rate limit | Descripción |
|--------|------|------------|-------------|
| POST | `/api/sheets/registro` | 5/min | Envía datos de diagnóstico al Sheet |
| POST | `/api/sheets/feedback` | 10/min | Envía feedback de utilidad al Sheet |
| POST | `/api/sheets/feedback-real` | 5/min | Envía enlace de feedback real al Sheet |
| GET | `/api/sheets/datos` | 5/min | Datos del Sheet para dashboard (requiere admin) |

### Admin
| Método | Ruta | Rate limit | Descripción |
|--------|------|------------|-------------|
| POST | `/api/admin/login` | 3/min | Login admin, devuelve cookie HttpOnly |
| POST | `/api/admin/logout` | — | Borra cookie de sesión admin |
| GET | `/dashboard?key=...` | — | Sirve dashboard (requiere cookie o key) |


---

## 6. Motor de diagnóstico

### 6.1 Señales extraídas del audio (extractor.py)

El extractor analiza el archivo de audio y produce ~50 data points:

- **Duración y tempo:** duración en segundos, BPM (detección automática o manual)
- **Curva de energía:** RMS por bloques de 8-16 compases, varianza entre bloques
- **Balance espectral:** energía en sub (<200Hz), low-mid (200-600Hz), mid (600-2kHz), high-mid (2-6kHz), high (>6kHz), air (>12kHz) — medido en mel-dB
- **Distribución de secciones:** número de bloques, ratio entre sección más larga y más corta, detección de intro/outro, bloques de baja energía largos
- **Densidad espectral:** spectral flatness promedio
- **Rango dinámico:** crest factor (peak/RMS)
- **Loudness:** LUFS integrado (pyloudnorm)
- **Mono compatibility:** correlación entre canales L/R
- **Harshness:** detección de picos en 2-5kHz
- **Tonalidad:** estimación de key (chroma features)

### 6.2 Diagnósticos disponibles (reglas.py)

El motor evalúa 9 hipótesis diagnósticas con un sistema de puntuación ponderada:

| # | Diagnóstico | Señal principal de audio | Señal principal de contexto |
|---|-------------|-------------------------|---------------------------|
| 1 | Problema de arreglo / estructura | Poca variación de energía, sin secciones diferenciables | Usuario en fase de idea o arreglo |
| 2 | Poco contraste entre secciones | Curva de energía plana, densidad uniforme | Reporta que "suena repetitivo" |
| 3 | Exceso de low-end | Energía desproporcionada en graves vs. medios | Cualquier contexto |
| 4 | Exceso de capas / densidad | Alta densidad espectral constante | "Suena lleno pero confuso" |
| 5 | Track verde / idea sin cerrar | Duración corta, sin estructura reconocible | En "fase de idea" |
| 6 | Mezcla prematura | Cruce: usuario dice mezclar pero track tiene problemas estructurales | Error de foco detectado |
| 7 | Carencia espectral | Falta de energía en medios o agudos | Cualquier contexto |
| 8 | Problemas de mono compatibility | Baja correlación L/R | Cualquier contexto |
| 9 | Sin diagnóstico significativo | Todas las puntuaciones < umbral mínimo (3) | Track bien producido |

### 6.3 Flujo del motor

1. **Extraer señales** (extractor.py) → ~50 data points del audio
2. **Calcular indicadores derivados** (reglas.py) → contraste_energetico, balance_grave, densidad_global, desarrollo_temporal, madurez_estimada, etc.
3. **Evaluar hipótesis** (reglas.py) → cada diagnóstico acumula puntuación basada en condiciones audio + contexto
4. **Aplicar jerarquía pedagógica** → estructura > contraste > densidad/balance > mezcla
5. **Generar feedback contextualizado** (contextualizador.py) → feedback didáctico por parámetro, ponderado según género e intención
6. **Renderizar templates** (templates.py) → diagnóstico principal, explicación, 3 prioridades, qué no tocar, siguiente sesión, estado del track

### 6.4 Inteligencia cruzada

El motor aplica reglas de cruce entre diagnósticos (reglas.py):
- Si hay problema estructural, nunca recomendar mezcla fina
- Si el usuario cree que su problema es mezcla pero el track es verde, señalar error de foco
- Balance espectral se pondera según género (no asumir balance plano universal)
- No contradecir datos medidos en el diagnóstico
- Umbral mínimo de confianza (score ≥ 3) para emitir diagnóstico


---

## 7. Autenticación y seguridad (v0.4.0)

### 7.1 Auth de usuarios
- Login/registro unificado en un solo endpoint (`/api/auth/acceder`)
- Contraseñas hasheadas con bcrypt (mínimo 8 caracteres)
- Tokens JWT con expiración a 7 días
- Usuarios almacenados en Google Sheets pestaña "usuarios" (email, password_hash, fecha_registro)

### 7.2 Auth admin
- Dashboard protegido por ADMIN_KEY (acceso inicial) + cookie HttpOnly JWT (sesión de 12h)
- Endpoint `/api/admin/login` con rate limit 3/min
- Cookie: HttpOnly, Secure, SameSite=strict

### 7.3 Medidas de seguridad implementadas (auditoría V-01 a V-10)

| ID | Vulnerabilidad | Fix |
|----|---------------|-----|
| V-01 | URL de Apps Script expuesta en frontend | Eliminada, todo va por proxy backend |
| V-02 | CORS abierto (*) | Restringido a mentotrack.com, www.mentotrack.com, localhost |
| V-03 | Tokens de sesión sin firma | JWT con HS256 + secret de 64 hex chars |
| V-04 | Dashboard sin auth real | ADMIN_KEY + cookie HttpOnly JWT |
| V-05 | Sin rate limiting | slowapi en todos los endpoints (3-10/min según endpoint) |
| V-06 | Contraseñas de 4 chars | Mínimo subido a 8 caracteres |
| V-07 | Endpoints de feedback sin auth | Requieren JWT válido |
| V-08 | JWT sin expiración | Expiración a 7 días |
| V-09 | Apps Script acepta GET (params en URL) | Todo migrado a POST con JSON body |
| V-10 | Dashboard accesible por URL directa | Acceso directo a dashboard.html bloqueado en catch-all |

### 7.4 Variables de entorno (Railway)
```
SHEETS_WEBHOOK=https://script.google.com/macros/s/[ID]/exec
JWT_SECRET=[64 hex chars]
ADMIN_KEY=[32 hex chars]
```


---

## 8. Google Apps Script (v2)

Archivo de referencia: `apps_script.js`

Todo funciona vía POST con JSON body. El doGet() devuelve error.

### Acciones soportadas

| action/tipo | Descripción | Campos |
|-------------|-------------|--------|
| `get_all` | Todos los datos (dashboard admin) | — |
| `get_user` | Buscar usuario por email | email |
| `register` | Registrar usuario nuevo | email, hash |
| `feedback_real` | Guardar enlace de feedback | email, enlace |
| `feedback_util` | Guardar valoración de utilidad | email, fue_util, comentario |
| `registro` | Nuevo diagnóstico | email, nombre_proyecto, formulario, diagnostico, senales_json |

### Columnas del Sheet principal
timestamp | email | nombre_proyecto | formulario | diagnostico | senales_json | fue_util | comentario | feedback_real


---

## 9. DNS y dominio

| Registro | Tipo | Nombre | Valor | Proxy | Función |
|----------|------|--------|-------|-------|---------|
| 1 | CNAME | @ (root) | cx9442g7.up.railway.app | Proxied | Cloudflare CNAME flattening + redirect rule |
| 2 | CNAME | www | cx9442g7.up.railway.app | DNS only | Tráfico directo a Railway (Railway gestiona SSL) |
| 3 | TXT | _railway-verify... | railway-verify=1... | DNS only | Verificación de dominio para Railway |

- Nameservers: blair.ns.cloudflare.com, jack.ns.cloudflare.com (configurados en Hostinger)
- Railway custom domain: www.mentotrack.com (SSL gestionado por Railway)
- IMPORTANTE: el CNAME de `www` debe estar en "DNS only" (nube gris) — Railway necesita verificar SSL directamente
- El CNAME de `@` (root) debe estar en "Proxied" (nube naranja) — Cloudflare gestiona SSL y aplica la redirect rule

### Redirect Rule (Cloudflare Rules)
- Nombre: "Redirect root to www"
- Tipo: Wildcard pattern
- Request URL: `https://mentotrack.com/*`
- Target URL: `https://www.mentotrack.com/${1}`
- Status code: 301 (Permanent Redirect)

### SSL/TLS (Cloudflare)
- Modo: Automatic SSL/TLS (Cloudflare recomienda "Full")
- Always Use HTTPS: activado
- Edge certificate: Universal, activo, cubre `*.mentotrack.com` y `mentotrack.com`


---

## 10. Branding

- **Nombre:** Mentotrack (antes TrackDiag)
- **Marca paraguas:** Producción Online
- **Colores:** #2C2C2C (dark), #4C4C4C (medium), #BCBCBC (light), #FFFFFF (white), #25F464 (verde flúor), #6D10FF (púrpura flúor)
- **Tipografía:** Termina Demi (títulos/logo), Arimo (cuerpo)
- **Logo:** Wordmark "mentotrack" con knob/onda verde integrada (SVG)
- **Landing:** Dos columnas — texto + logo (izq), drop zone de audio (der), fondo oscuro


---

## 11. Flujo del usuario

1. **Landing** → arrastra/selecciona archivo de audio (WAV, MP3, FLAC, AIFF)
2. **Cuestionario** → 6-8 preguntas (género, fase, objetivo, bloqueo, experiencia, dificultad)
3. **Procesamiento** → extracción de señales + motor de reglas (5-15 seg)
4. **Diagnóstico** → diagnóstico principal, explicación, 3 prioridades, qué no tocar, siguiente sesión, estado del track (semáforo), gráfico de barras del espectro, datos técnicos
5. **Feedback** → valoración de utilidad + opción de solicitar track review manual de Alex
6. **Panel de usuario** → historial de diagnósticos anteriores (requiere login)


---

## 12. Validación del motor

Se realizaron dos rondas de validación con 8 tracks reales (ver `fase0-validacion-resultados.md`):

**v0.1:** 2 aciertos fuertes, 3 parciales, 2 débiles, 1 error
**v0.2:** 4 aciertos fuertes, 3 parciales, 0 débiles, 0 errores

Las mejoras clave fueron: análisis de distribución de secciones (no solo si hay variación, sino cómo se distribuye), mayor peso del contexto del usuario en el estado del track, umbral mínimo de confianza (score ≥ 3), y ajuste de umbrales espectrales por contexto.

**Punto ciego permanente:** problemas armónicos/melódicos (disonancias, tonalidad incorrecta). El motor no puede detectarlos con análisis de señal básico. Limitación asumida.

Posteriormente se procesaron 17 tracks adicionales (audios 9-25) para calibración continua.


---

## 13. Decisiones de diseño importantes

**¿Por qué Google Sheets y no una DB real?**
Para el MVP, Google Sheets permite inspección visual directa de los datos, edición manual (columna revision_alex), y cero coste de infraestructura. Es suficiente para cientos de usuarios. Se migrará cuando sea necesario.

**¿Por qué templates en vez de LLM?**
Los templates escritos a mano son más controlables, consistentes y baratos. Un LLM genera texto "bonito" pero impredecible. El tono y la utilidad del texto se controlan mejor con templates bien escritos.

**¿Por qué motor de reglas en vez de ML?**
Con pocos datos de entrenamiento, un motor de reglas explicable es más fiable y depurable que un modelo de ML. Las reglas codifican el conocimiento pedagógico de Alex. Se puede migrar a ML cuando haya suficientes datos etiquetados.

**¿Por qué single-file frontend?**
Minimiza complejidad de build/deploy. Sin webpack, sin node_modules, sin build step. El HTML se sirve directamente con FastAPI. Para una app de esta escala, es la decisión correcta.

**¿Por qué POST-only en Apps Script?**
Seguridad. Los parámetros de URL (GET) quedan en logs de servidor, historial del navegador, y se pueden interceptar. Los datos sensibles (hashes de contraseña) solo deben viajar en el body de un POST.


---

## 14. Cómo desarrollar localmente

```bash
cd trackdiag/backend
pip install -r requirements.txt
python3 -m uvicorn main:app --reload --port 8000
```

Abrir http://localhost:8000 en el navegador.

Variables de entorno opcionales para desarrollo local:
```bash
export SHEETS_WEBHOOK="https://script.google.com/macros/s/[ID]/exec"
export JWT_SECRET="cualquier-string-para-desarrollo"
export ADMIN_KEY="clave-local"
```

Sin SHEETS_WEBHOOK, el login/registro y el guardado en Sheets no funcionarán, pero el diagnóstico sí (se procesa localmente).


---

## 15. Deploy

### Railway (producción)
- Auto-deploy en push a main en GitHub
- Dockerfile en la raíz de `trackdiag/`
- Variables de entorno configuradas en Railway dashboard
- Custom domain: www.mentotrack.com

### Apps Script
- Abrir script.google.com → proyecto Mentotrack
- Pegar contenido de `apps_script.js`
- Deploy → Nueva implementación → Web app → Cualquier usuario
- Copiar URL y actualizar SHEETS_WEBHOOK en Railway si cambia


---

## 16. Historial de versiones

| Versión | Fecha | Cambios principales |
|---------|-------|---------------------|
| 0.1 | Abril 2026 | Motor de reglas v0.1, 5 diagnósticos, validación con 8 tracks |
| 0.2 | Abril 2026 | Motor v0.2: distribución de secciones, umbral mínimo, ajuste espectral. 4 diagnósticos más |
| 0.3 | Abril 2026 | 9 diagnósticos, LUFS, mono compatibility, harshness, análisis armónico, gráfico de barras espectral, feedback contextualizado, panel de usuario, dashboard admin, rebrand a Mentotrack |
| 0.4 | 24 Abril 2026 | Auditoría de seguridad completa (V-01 a V-10): JWT auth, CORS restringido, rate limiting, bcrypt, POST-only Apps Script, dashboard protegido. Deploy en dominio www.mentotrack.com |
| 0.4.1 | 24 Abril 2026 | DNS completo: redirect mentotrack.com → www, SSL verificado, Always Use HTTPS, Cloudflare Automatic SSL/TLS, documentación unificada |


---

## 17. Performance y cold starts

Railway (plan free/Hobby) pone los servicios a dormir tras ~30 min sin tráfico. El cold start puede tardar 10-15 segundos porque tiene que cargar Python + librosa + numpy + scipy. Opciones para mitigarlo:

### Soluciones sin cambiar de plan
1. **Cron/health-check ping:** Configurar un servicio externo (UptimeRobot, cron-job.org) que haga un GET a `https://www.mentotrack.com/` cada 10-15 minutos. Esto mantiene el servicio despierto. Coste: gratis.
2. **Lazy imports de librosa:** Mover los imports pesados (`librosa`, `scipy`) dentro de las funciones que los usan en vez de importarlos al nivel del módulo. Reduce el tiempo de arranque pero no elimina el cold start.
3. **Reducir imagen Docker:** Usar builds multi-stage para reducir el tamaño de la imagen. Menos peso = arranque más rápido.

### Soluciones con coste
4. **Railway Pro ($5/mes):** El plan Pro no duerme los servicios. Es la solución más directa y limpia.
5. **Cambiar región:** Railway asigna región automáticamente. En plan Pro se puede elegir región (ej: `eu-west` para audiencia española/europea) lo que reduciría latencia significativamente.
6. **Fly.io o Render (alternativas):** Ambos tienen opciones de always-on en free tier con limitaciones, o planes baratos.

### Optimizaciones de frontend (sin coste)
7. **Preload de fuentes:** Añadir `<link rel="preload">` para Termina Demi y reducir el CLS.
8. **Caché de assets:** Configurar headers `Cache-Control` en FastAPI para servir los archivos estáticos con caché agresivo.
9. **Comprimir respuestas:** Activar gzip/brotli en FastAPI con middleware de compresión.


---

## 18. Próximos pasos potenciales

- Push del apps_script.js y MENTOTRACK.md al repo GitHub (consistencia)
- Implementar health-check ping para evitar cold starts
- Opción de descarga de informe en PDF
- Comparación entre versiones de un mismo track
- Integración con recursos formativos (tutoriales YouTube de Alex)
- Dashboard con métricas más avanzadas
- Migración de Google Sheets a DB real cuando el volumen lo justifique
