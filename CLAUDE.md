# CLAUDE.md — Guía operativa para Claude Code

Documento de referencia para trabajar en este repo. Para la visión completa del producto y arquitectura consultar `MENTOTRACK.md` (puede estar desactualizado: ver §"Estado actual" abajo).

---

## Identidad

**Mentotrack** — app web de diagnóstico pedagógico para productores de música electrónica. Sube un bounce + cuestionario → diagnóstico priorizado.

- Dominio: www.mentotrack.com (Railway + Cloudflare)
- Marca: Producción Online (PRODONLINE LLC, Delaware)
- Repo privado en GitHub. Rama de trabajo `dev`; merge a `main` dispara el auto-deploy.

---

## Estado actual (mayo 2026)

`MENTOTRACK.md` quedó en v0.4.1 (24 abril). Cambios posteriores relevantes (resumen — para detalle ver `frontend/changelog.json`):

- **API version actual:** `0.5.26` (en `/api/health` y en `FastAPI(...)`).
- **DB primaria: PostgreSQL en Railway** (`backend/db.py` con pool asyncpg). **Cutover B cerrado completamente el 2026-05-27**: Postgres es la fuente única. El self-heal bulk de v0.5.21 copió 315 de 316 hashes residuales `__MIGRATED__` desde Sheets a Postgres; queda 1 usuario residual sin hash real (no encontrado en Sheets) que tendrá que usar /forgot password manual si quiere volver. Los flujos de auth (`/login`, `/acceder`, `/register`) son Postgres-only. La variable `SHEETS_WEBHOOK` ya solo la usan los endpoints admin `/api/admin/cutover-b*` por si hay que repetir la operación con casos edge — se puede desactivar en Railway cuando se confirme que no hace falta más.
- **Proyectos + versiones** (feat 0.5.3): un análisis pertenece a un proyecto y se numera (`v1`, `v2`…) con etiqueta opcional. El panel del usuario unifica el listado, marca el proyecto/versión de cada análisis y permite asignar inline los huérfanos. Detalle de proyecto con barra de "listo para sello" y cambios entre versiones en lenguaje de escucha.
- **Tracking de tutoriales YouTube:** clicks guardados en Postgres (con espejo a Sheets) vía `/api/sheets/tutorial-click`.
- **Página `/ideas`:** propuestas con votación (`/api/ideas`, voto toggle).
- **Auth ampliado:** `/api/auth/acceder` unificado + `/login`, `/register`, `/check_username`, `/set_username`, `/forgot`. Modal flotante en el flow de upload.
- **PWA admin:** dashboard instalable en móvil (`manifest-admin.json`, `sw-admin.js`).
- **Páginas legales:** `/aviso-legal`, `/privacidad`, `/cookies`, `/terminos`, `/changelog`.
- **Seguridad extra:** bloqueo de `.git` y `dashboard.html` en el catch-all, límite de upload 100 MB validado en cliente y servidor.

### Tamaños actuales
- `backend/main.py` — ~1900 líneas
- `backend/repositories.py` — ~550 líneas (capa SQL)
- `backend/db.py` — ~90 líneas (pool asyncpg)
- `frontend/index.html` — ~3300 líneas / ~210 KB
- `frontend/dashboard.html` — ~1480 líneas / ~90 KB

---

## Estructura de archivos

```
trackdiag/
├── Dockerfile
├── MENTOTRACK.md              # Doc de producto/arquitectura (puede estar desfasada)
├── CLAUDE.md                  # Este archivo
├── apps_script.js             # Apps Script v2 (referencia, se pega en Google)
├── apps_script_COPIAR.js      # Versión a copiar/pegar (puede divergir)
├── docs/
│   ├── apps-script-completo.js
│   ├── apps-script-ideas.js
│   └── apps-script-tutorial-click.js
├── backend/
│   ├── main.py                # FastAPI app (endpoints + routing)
│   ├── repositories.py        # Capa SQL (asyncpg + decorador @with_retry)
│   ├── db.py                  # Pool asyncpg, init/close, setup ping
│   ├── requirements.txt
│   ├── sesiones.jsonl         # Log local (gitignored)
│   ├── alembic/               # Migraciones de schema (Postgres)
│   │   ├── env.py, script.py.mako
│   │   └── versions/          # Una por migración
│   ├── scripts/
│   │   └── migrate_sheets_to_postgres.py   # One-shot: copia Sheets → Postgres
│   └── engine/
│       ├── extractor.py       # ~50 señales de audio (incluye true_peak_dbtp 4x oversampling)
│       ├── reglas.py          # 9 hipótesis diagnósticas ponderadas
│       ├── diagnostico.py     # Orquestador
│       ├── contextualizador.py
│       └── templates.py
└── frontend/
    ├── index.html             # SPA principal (React+Tailwind, single-file)
    ├── dashboard.html         # Admin (PWA-capable)
    ├── ideas.html             # Página de propuestas con votación
    ├── changelog.html         # Renderiza changelog.json
    ├── changelog.json         # Historial de versiones (canónico)
    ├── aviso-legal.html, privacidad.html, cookies.html, terminos.html
    ├── manifest-admin.json, sw-admin.js, pwa-admin-{192,512}.png
    ├── robots.txt, sitemap.xml, favicon.svg, og-image.{png,svg}
    ├── logo.svg, Termina-Demi.{woff,woff2}
    └── legal.css
```

---

## Stack (resumen)

- **Backend:** Python 3.11 + FastAPI 0.115 + librosa 0.11 + pyloudnorm + scipy/numpy. Auth: bcrypt + PyJWT. Rate limit: slowapi.
- **DB:** PostgreSQL 18 en Railway (asyncpg). Sheets sobrevive temporalmente como espejo (cutover B).
- **Frontend:** Single-file React+Tailwind (CDN), sin build step. JSX transformado en cliente con Babel standalone.
- **Hosting:** Railway (auto-deploy en push a `main`). Cloudflare para DNS/SSL/redirect root→www.

### Variables de entorno (Railway)
```
DATABASE_URL      # postgresql://...  (Railway inyecta la interna: postgres.railway.internal)
SHEETS_WEBHOOK    # URL del Apps Script deployado (espejo durante cutover B)
JWT_SECRET        # 64 hex chars
ADMIN_KEY         # cualquier string razonable
```

### Desarrollo local con DB real

`postgres.railway.internal` no resuelve fuera de Railway. Para tocar la DB de prod desde local usar **Railway CLI**:

```bash
brew install railway   # o npm i -g @railway/cli
railway login
railway link           # elige el proyecto extraordinary-tranquility y el servicio Mentotrack
railway variables --service Postgres | grep DATABASE_PUBLIC_URL  # URL pública (proxy TCP)
```

Esa URL pública (`ballast.proxy.rlwy.net:NNNN`) se puede usar como `DATABASE_URL` en local. **No commitear** ese valor — está bajo `.gitignore` el escenario habitual de exports.

---

## Convenciones del repo

### Idioma
- **Commits, comentarios, mensajes al usuario y UI:** español.
- Excepción: identificadores de código en inglés cuando ya es el patrón (variables, funciones).

### Estilo de commits
Mira `git log --oneline` para calibrar tono. Patrones que se usan:
- `fix: <qué se arregló>` — bugfixes
- `feat: <nueva funcionalidad>` — features
- `dashboard: <cambio>` / `security: <cambio>` — prefijo por área cuando aplica
- `chore: <limpieza>` — refactors/tooling
- Mensaje corto en una línea suele ser suficiente. Cuerpo solo si el "por qué" no es obvio.
- Co-author footer de Claude solo cuando Claude hizo el grueso del trabajo.

### Branches
- Rama de trabajo: `dev`. Mergear a `main` cuando el cambio esté revisado y probado.
- Push a `dev` **no** despliega — sólo `main` dispara Railway.

### No tocar sin pedir
- **`apps_script.js` / `docs/apps-script-*.js`:** son referencia para pegar en Google Apps Script. Cambiar el archivo aquí NO actualiza producción — Alex tiene que pegarlo manualmente en script.google.com. Avisar siempre.
- **DNS / Cloudflare / Railway envs:** se gestionan en sus dashboards, no en el repo.
- **`backend/sesiones.jsonl`:** está gitignored a propósito (log local).
- **Tipografías `Termina-Demi.*`:** licenciadas, no regenerar/sustituir.

### Frontend single-file
- `index.html` y `dashboard.html` son SPAs autocontenidas. Sin webpack, sin node_modules.
- React + Tailwind cargados por CDN, JSX transformado en cliente con Babel standalone.
- Para cambios pequeños usar `Edit` con suficiente contexto (el archivo es grande, `old_string` debe ser único).
- El componente `SelectField` compara `value === opt.value` para marcar la opción en morado. Si rellenas valores programáticamente (p.ej. prefill desde otro proyecto), pasa el `value` (`tech_house`), no el label (`Tech House`). El `formulario` en Postgres guarda labels — mapea label → value antes de meterlo en `contexto`.

### Backend
- Todos los endpoints de cara al exterior pasan por slowapi rate limit.
- Endpoints sensibles (`/api/feedback*`, `/api/auth/historial`, `/api/proyectos*`) requieren JWT en header `Authorization: Bearer`.
- Endpoints `/api/sheets/*` son legacy en el nombre (frontend desplegado los usa), pero internamente solo escriben a Postgres tras el cierre del cutover B. No mantienen espejo a Sheets.
- Patrón de fallback Sheets: SOLO usado para autenticación de usuarios `__MIGRATED__`. Cualquier otra escritura/lectura es Postgres-only; si falla, 503 directo.
- Si añades un endpoint nuevo, regístralo también en el catch-all si debe servir HTML.
- Capa SQL en `repositories.py`: cada función decorada con `@with_retry()` para mitigar cortes intermitentes del proxy TCP de Railway. No usar el pool sin el decorador.

### CORS
Limitado a `mentotrack.com`, `www.mentotrack.com`, `localhost`. Cualquier dominio nuevo (preview de Railway, staging) requiere añadirlo en `main.py`.

---

## Flujo de trabajo

### Desarrollo local
```bash
cd backend
pip install -r requirements.txt
DATABASE_URL="..." SHEETS_WEBHOOK="..." JWT_SECRET="..." ADMIN_KEY="..." \
  python3 -m uvicorn main:app --reload --port 8000
```
Sin `DATABASE_URL` la mayoría de endpoints caen a Sheets (más lento, sin proyectos). Sin `SHEETS_WEBHOOK` el diagnóstico funciona pero no hay espejo.

### Migraciones de schema
```bash
cd backend
DATABASE_URL="..." alembic revision --autogenerate -m "descripción"
DATABASE_URL="..." alembic upgrade head   # opcional en local, prod lo hace solo al desplegar
```
Revisar la migración generada antes de aplicarla — `autogenerate` no detecta cambios de datos.

**En producción la migración corre sola al arrancar la app** (`_run_alembic_upgrade` en `main.py` ejecuta `alembic upgrade head` en el startup event). Por tanto basta con mergear a `main`: Railway despliega → la app arranca → si hay migraciones pendientes se aplican antes de inicializar el pool. Si la migración falla, se logea y la app sigue arrancando con la DB desactualizada.

### Deploy
- Trabajo en `dev`, merge a `main` cuando esté revisado.
- Push a `main` → Railway construye con `Dockerfile` y despliega.
- No hay branch de staging. Cambios delicados se prueban con upload local apuntando a Postgres real (vía Railway CLI) o se separan en commits pequeños para poder revertir.

### Cambios en Apps Script
1. Editar `apps_script.js` (o el archivo específico en `docs/`) en el repo.
2. **Avisar al usuario** que tiene que pegar el contenido en script.google.com → Deploy → Nueva implementación.
3. Si la URL del deploy cambia, hay que actualizar `SHEETS_WEBHOOK` en Railway.

### Cambios en el changelog
- Editar `frontend/changelog.json` (es el canónico). `frontend/changelog.html` lo renderiza.
- El array `entries` va en orden descendente; la entrada más reciente arriba.
- Bumpear también la versión en `backend/main.py` (`FastAPI(...)` + `/api/health`).

---

## Notas de seguridad activas

Auditoría V-01 a V-10 cerrada (ver `MENTOTRACK.md §7.3`). Reglas vivas:
- JWT obligatorio para endpoints autenticados, expira a 7 días.
- Contraseñas mínimo 8 chars, bcrypt.
- Dashboard admin: cookie HttpOnly+Secure+SameSite=strict, ADMIN_KEY como fallback inicial.
- Apps Script POST-only (params en URL filtraban hashes).
- Acceso directo a `dashboard.html` y a `.git/*` bloqueado en el catch-all.
- Upload máx 100 MB (validado en cliente y servidor), magic bytes verificados además de extensión.
- **Tras el cutover B**: rotar password de Postgres y desactivar Public Networking en Railway.

---

## Punto ciego conocido del motor

El motor de diagnóstico **no detecta problemas armónicos/melódicos** (disonancias, tonalidad incorrecta). Asumido como limitación del análisis de señal básico — no proponer "fix" para esto sin un cambio de stack (ML/embeddings).

---

## Cómo mantener este archivo

Actualizar CLAUDE.md cuando:
- Cambie la estructura de carpetas (nuevo dir, mover archivos).
- Se añada un endpoint o se rompa una convención existente.
- Cambien las variables de entorno requeridas.
- Se haga un cambio que altere el flujo de deploy o la rama de trabajo.

Para todo lo demás (decisiones de producto, historia detallada de versiones, motor de reglas), actualizar `MENTOTRACK.md` o `frontend/changelog.json`.
