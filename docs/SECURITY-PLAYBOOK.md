# Security Playbook — patrones y proceso de seguridad (portable)

> **Para quién es esto:** para ti, Claude, trabajando en OTRO proyecto de Alex.
> Es el destilado de cómo se hace seguridad en **Mentotrack** (FastAPI + Postgres
> + frontends single-file) para que lo repliques. No es teoría OWASP genérica:
> son los **patrones concretos** y, sobre todo, el **proceso** que usamos para
> encontrar y cerrar vulnerabilidades. Adapta los idioms a tu stack; los
> principios y el proceso son los mismos.

> **Cómo usarlo:** (1) lee la filosofía, (2) aplica el catálogo de controles según
> lo que el proyecto exponga, (3) **corre el proceso de revisión adversarial antes
> de cada lanzamiento o cambio sensible** — esa parte es la más valiosa.

---

## 0. Filosofía (los 7 principios que rigen todo)

1. **Valida en la frontera, no en el interior.** Todo input de cara al exterior
   (body, query, path, ficheros, headers) se valida/sanea en el punto de entrada.
   Nada que venga de fuera se considera de confianza.
2. **Fail closed (cierra por defecto).** Ante la duda, deniega. Un check que falla
   devuelve 403/404, no "deja pasar por si acaso". Los gates por defecto están en
   "denegado" y se abren explícitamente.
3. **Defensa en profundidad.** Cada vector tiene ≥2 capas (ej. subida de imagen:
   tipo + tamaño + magic/decoder + recompresión + límite de dimensiones). Si una
   falla, otra cubre.
4. **Menor privilegio y menor exposición.** Los endpoints públicos devuelven solo
   los campos públicos (nunca email, hash, IDs internos innecesarios). El acceso
   se concede por rol/propiedad, no globalmente.
5. **Secretos fuera del código, siempre.** Cero credenciales en el repo. Todo por
   variable de entorno. El repo es público o se filtra: actúa como si lo fuera.
6. **No reinventes cripto ni parsing.** Usa librerías probadas (PyJWT, bcrypt,
   Pillow, `hmac.compare_digest`). Re-codifica/normaliza en vez de "inspeccionar"
   contenido hostil.
7. **El proceso > el control puntual.** Un control aislado caduca; un **proceso de
   revisión adversarial repetible** encuentra lo que no sabías que tenías. Ver §12.

---

## 1. Autenticación y sesiones

**Qué protege:** identidad del usuario, expiración automática, separación de roles.

**Patrones concretos (Mentotrack):**
- **JWT de usuario:** PyJWT, **HS256**, claim `sub` = email, `iat`/`exp`,
  expiración 7 días. Se viaja en `Authorization: Bearer <token>`.
  ```python
  payload = {"sub": email, "iat": now_utc, "exp": now_utc + timedelta(days=7)}
  token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
  # verificar: jwt.decode(token, JWT_SECRET, algorithms=["HS256"]) -> sub | None
  ```
- **Contraseñas:** `bcrypt` (salt incluido), **mínimo 8 chars** validado en server.
  Nunca se loguean ni se devuelven.
- **Admin separado del usuario:** sesión admin en **cookie HttpOnly + Secure +
  SameSite=strict**, firmada con un secreto DISTINTO (`ADMIN_SESSION_SECRET`),
  expiración corta (12h). Razón: la cookie HttpOnly no es robable por XSS, y el
  panel admin no comparte secreto ni superficie con el JWT de usuario.
- **Helpers en capas (compón, no copies):**
  - `_optional_auth_user(request)` → email o None (para vistas que adaptan UI).
  - `_require_auth_user(request)` → (email, error). Si no hay sesión, 401.
  - `_require_comunidad(request)` → auth + check de acceso al recurso (403 si no).
  Cada endpoint llama al helper del nivel que necesita; el control vive en un sitio.
- **Unicidad de username case-insensitive** (anti-suplantación @Alex/@alex):
  índice único funcional `UNIQUE (LOWER(username))`, no `UNIQUE (username)`.
- **Invalidación de sesión por `token_version` (revocación de JWT):** el JWT es
  *stateless* → por defecto no se puede revocar antes de `exp`. Solución: una
  columna `token_version INTEGER DEFAULT 0` por usuario; el token lleva el claim
  `tv` con ese valor al emitirse. Al **cambiar la contraseña** (reset) se hace
  `token_version += 1`, lo que **expulsa todos los tokens previos**. La comprobación
  vive en UN **middleware global** (no se toca cada endpoint): si el `tv` del token
  ≠ `token_version` de la DB → 401.
  ```python
  # al emitir: payload["tv"] = user.token_version
  # middleware (una sola vez, global):
  class TokenVersionMiddleware(BaseHTTPMiddleware):
      async def dispatch(self, request, call_next):
          auth = request.headers.get("Authorization", "")
          if auth.startswith("Bearer ") and db_up():
              try:
                  p = jwt.decode(auth[7:], SECRET, algorithms=["HS256"])
                  email, tv = p.get("sub"), int(p.get("tv", 0) or 0)
              except Exception:
                  email = None                      # firma mala → lo gestiona el endpoint
              if email:
                  try:
                      actual = await get_token_version(email)
                      if actual is not None and actual != tv:
                          return JSONResponse(401, {"error": "sesión caducada"})
                  except Exception:
                      pass                          # FAIL-OPEN ante error de DB
          return await call_next(request)
  # al resetear contraseña: await bump_token_version(user_id)  # token_version += 1
  ```
  Claves de diseño: **fail-open** ante error de DB (no rompe a usuarios legítimos
  en un corte; el endpoint validará igual); **retrocompatible** (tokens emitidos
  antes de existir la feature no llevan `tv` → se tratan como 0 = default → siguen
  válidos hasta el primer reset); **un solo punto de enforcement** (el middleware)
  en vez de tocar los N call-sites de auth. Coste: una query pequeña e indexada por
  request autenticada — asumible.

**Cómo replicar:**
1. `SECRET = secrets.token_hex(32)` desde env, con fallback aleatorio + warning si falta.
2. JWT HS256 con `exp` y `tv`. Verifica SIEMPRE con `algorithms=[...]` explícito
   (evita el ataque `alg=none`).
3. bcrypt para passwords, min 8. Rol admin con cookie HttpOnly/Secure/SameSite y
   secreto propio.
4. Define 2-3 helpers de auth en capas y úsalos; no repitas la lógica por endpoint.
5. `token_version` + middleware global para poder **revocar sesiones** al cambiar la
   contraseña (o ante compromiso). Es la pieza que le falta a un JWT puro.

---

## 2. Autorización a nivel de objeto (IDOR)

**Qué protege:** que un usuario no toque recursos de otro (el bug nº1 en apps con login).

**Patrones concretos:**
- **La propiedad se comprueba en el WHERE, no en Python.** El UPDATE/DELETE incluye
  `AND usuario_id = $2`; si afecta 0 filas → 404 "no es tuyo". No "lee, compara en
  app, luego escribe" (eso es racy y se olvida).
  ```python
  # editar solo si eres el dueño — atómico, sin TOCTOU
  res = await conn.execute(
      "UPDATE posts SET titulo=$3 WHERE id=$1 AND usuario_id=$2 AND activo", ...)
  return res.endswith(" 1")
  ```
- **Override de moderador explícito:** una función `_mod` separada que NO filtra por
  dueño, invocada SOLO tras `_es_moderador(email)` (allowlist por env). Dos caminos
  claros (dueño vs moderador), nunca un "god mode" implícito por parámetro None.
- **El cliente nunca decide la autorización.** Flags como `es_propietario`/`es_autor`
  se calculan en el servidor comparando el `usuario_id` del recurso con el del viewer
  (resuelto del JWT); se mandan al front solo para pintar botones. El backend
  RE-valida en cada acción.
- **No expongas PII ni IDs innecesarios.** El endpoint de perfil público hace
  `SELECT username, foto, bio, ...` — jamás `email`/`password_hash`. El `usuario_id`
  se usa internamente para `es_propietario` pero NO se serializa.

**Cómo replicar:** toda mutación lleva el dueño en el WHERE; el rol elevado es un
camino explícito tras un check explícito; los endpoints públicos tienen una lista
blanca de campos, no un `SELECT *`.

---

## 3. Validación de entrada e inyección (SQLi)

**Qué protege:** SQL injection, payloads sobredimensionados, IDs basura.

**Patrones concretos:**
- **SQL SIEMPRE parametrizado** (`$1, $2` en asyncpg / placeholders del driver).
  CERO f-strings/concatenación con datos del usuario. Esto elimina SQLi de raíz.
  (La única interpolación permitida es de identificadores controlados por el código,
  ej. construir el nombre de un índice en una migración — nunca datos de usuario.)
- **`_sanitize(texto, max_len)`** centralizado: recorta a longitud, limpia control
  chars; se aplica a todo texto libre (título, bio, mensaje, comentario, motivo de
  reporte) con caps explícitos (120, 300, 500…).
- **Parseo estricto de IDs:** `uuid.UUID(post_id)` en `try/except` → si no es UUID,
  404 inmediato. Nunca se mete el string crudo en una query.
- **Números acotados:** `_parse_float(v, min, max)` para BPM, LUFS, etc.

**Cómo replicar:** driver parametrizado siempre; un único `sanitize(text, cap)`;
valida el FORMATO de cada id/enum antes de usarlo (UUID, allowlist de valores).

---

## 4. Hardening de subida de ficheros (el vector más peligroso)

**Qué protege:** RCE/DoS/almacenamiento vía uploads. Es donde más se invierte.

### 4.1 Audio
- **Allowlist de extensión** + **límite de tamaño** (rechazo antes de procesar) +
  **magic bytes** (los primeros bytes deben corresponder al formato; impide renombrar
  un ejecutable a `.mp3`) + **límite de duración** (8s–20min, acota coste de
  transcode/análisis y cuelgues por ficheros de horas).
- El original va a un **tmp efímero**, se valida/transcodea, y solo el resultado
  final llega al volumen persistente. La RAM del original se libera (`content=None`).

### 4.2 Imágenes / avatar (caso de estudio — varias capas)
La clave: **no inspeccionar la imagen hostil, RE-CODIFICARLA.**
```python
def _procesar_avatar(content: bytes) -> bytes | None:
    Image.open(BytesIO(content)).verify()          # ¿es imagen real?
    im = Image.open(BytesIO(content))               # reabrir (verify la invalida)
    if im.format not in ("JPEG","PNG","WEBP"): return None   # allowlist de formato
    if getattr(im, "is_animated", False): return None        # anti frame-bomb (DoS RAM)
    w, h = im.size
    if w*h > 24_000_000 or w > 8000 or h > 8000: return None  # anti decompression-bomb
    im.draft("RGB", (512, 512))                     # JPEG: decodifica a escala -> menos RAM
    im = ImageOps.exif_transpose(im).convert("RGB") # respeta orientación, quita EXIF
    im = ImageOps.fit(im, (256, 256))               # recorte/resize fijo
    out = BytesIO(); im.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()                           # SALIDA re-codificada = payload neutralizado
```
Por qué cada capa:
- **Allowlist de formato:** no confíes en el content-type ni la extensión.
- **Rechazo de animadas:** un WebP/PNG animado carga TODOS los frames en RAM aunque
  uses uno → OOM. `is_animated` lo corta.
- **Cap de dimensiones/píxeles ANTES de decodificar:** una imagen pequeña puede
  declarar millones de píxeles (decompression bomb) y reventar memoria al
  decodificar. Limita `w*h` y el lado.
- **`draft()` para JPEG:** decodifica a escala reducida (1/2,1/4,1/8) → memoria
  acotada incluso con headers inflados.
- **Re-codificar a JPEG:** la salida es un JPEG limpio generado por ti →
  neutraliza polyglots, EXIF malicioso, chunks raros. El fichero del atacante se
  descarta.

### 4.3 Volumen / almacenamiento
- **Chequeo de espacio en disco** (`shutil.disk_usage`) antes de escribir; si el
  volumen está casi lleno, rechaza con 503 en vez de corromper la feature para todos.
- **Cuota por usuario** (ej. máx 3 ficheros activos) para acotar abuso de storage.

**Cómo replicar:** para cualquier upload → allowlist de tipo + cap de tamaño +
validación con decoder de la librería + **re-generar el artefacto** (transcode/
re-encode) en vez de servir el original; límites de dimensión/duración/frames;
chequeo de disco + cuota.

---

## 5. Servido de media y control de acceso (el patrón de URL firmada)

**El problema:** un `<img>`/`<audio>` no puede mandar `Authorization`. Si gateas el
endpoint con JWT, rompes la reproducción/carga. Pero servir el fichero "público por
id" filtra contenido privado.

**La solución (URL firmada HMAC temporal):**
- El endpoint **ya gateado** que lista los recursos (ej. el muro, que exige sesión)
  genera por cada recurso una URL con **firma HMAC + caducidad**:
  ```python
  exp = now_unix + 12*3600
  sig = hmac.new(SECRET, f"{id}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
  url = f"/api/audio/{id}?exp={exp}&sig={sig}"
  ```
- El endpoint de media valida firma + caducidad con **comparación de tiempo
  constante** (anti timing attack):
  ```python
  if exp < now_unix: return 403
  esperado = hmac.new(SECRET, f"{id}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
  if not hmac.compare_digest(esperado, sig or ""): return 403
  ```
- Resultado: solo quien pasó por el recurso gateado (un miembro) obtiene una URL
  válida, y caduca. Un anónimo con el id pelado → 403. Mantiene Range/seek (los
  query params no afectan al streaming por rangos).

**Variante para recursos no sensibles (avatares):** servir por **nombre de fichero
aleatorio** (`uuid4().hex + .jpg`) validado con **regex anclada anti path-traversal**:
```python
if not re.match(r"^[0-9a-f]{32}\.jpg$", filename): return 404   # no '..' ni '/'
```
Nombre no enumerable + regex estricta = acceso público aceptable sin auth.

**Cómo replicar:** media privada servida a tags HTML → **URL firmada temporal** desde
el endpoint gateado + `compare_digest`. Media no sensible → nombre opaco + validación
de nombre con regex anclada (jamás construyas la ruta con input sin validar).

---

## 6. Rate limiting

**Qué protege:** fuerza bruta, spam, scraping, DoS de endpoints caros.

**Patrón:** `slowapi` con límite POR RUTA según el coste/sensibilidad:
- Login: `5/minute` (anti fuerza bruta). Análisis pesado: `3/minute`.
- Compartir/reportar: `10/hour` (acciones caras/abusables). Listados: `30-60/minute`.
- Servir media: `120-300/minute` (legítimo cargar muchas miniaturas).

**Cómo replicar:** rate limit en TODOS los endpoints externos, con el número
ajustado al coste y al riesgo de abuso de cada uno (no un único límite global).
En entornos con proxy (Railway/Cloudflare), verifica que el límite usa la IP real
(`X-Forwarded-For`) y no la del proxy.

---

## 7. CORS y cabeceras de seguridad HTTP

### 7.1 CORS
**Patrón:** lista blanca de orígenes (`mentotrack.com`, `www.`, `localhost`),
métodos EXPLÍCITOS (`GET, POST, PATCH, DELETE`), `allow_credentials=False`.
Nunca `*` con credenciales. Si añades un método nuevo (p. ej. PATCH), recuerda
añadirlo aquí (aunque mismo-origen no haga preflight, evita sorpresas).

### 7.2 Cabeceras de seguridad (un middleware, todas las respuestas)
**Qué protege:** clickjacking, MIME-sniffing, downgrade a HTTP, fuga de referrer,
inyección de recursos/scripts (XSS). Un solo middleware las pone en TODAS las
respuestas:
```python
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        r = await call_next(request)
        r.headers["X-Content-Type-Options"] = "nosniff"          # no adivinar MIME
        r.headers["X-Frame-Options"] = "DENY"                    # no embeder en iframe
        r.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        r.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        r.headers["Content-Security-Policy"] = CSP               # ver abajo
        if request.url.scheme == "https":                        # HSTS solo en https
            r.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return r
```
- **`X-Content-Type-Options: nosniff`** — el navegador respeta el Content-Type, no
  "adivina" (impide que un upload se ejecute como script).
- **`X-Frame-Options: DENY`** + **CSP `frame-ancestors 'none'`** — anti-clickjacking
  (las dos: la cabecera para navegadores viejos, `frame-ancestors` la moderna).
- **`Referrer-Policy: strict-origin-when-cross-origin`** — no filtra la URL completa
  (con tokens en query, etc.) a sitios externos.
- **`Strict-Transport-Security` (HSTS)** — fuerza HTTPS en futuras visitas. Ponla
  SOLO sobre https. `includeSubDomains` si controlas todos los subdominios. `preload`
  es un compromiso fuerte y difícil de revertir → solo si estás seguro.
- **`Permissions-Policy`** — desactiva APIs que no usas (cámara, micro, geo).

**CSP (Content-Security-Policy) — la importante y la más delicada.** Restringe de
DÓNDE se cargan scripts/estilos/imágenes/conexiones. Para una app que carga React,
Tailwind y Babel por CDN y usa scripts inline:
```
default-src 'self';
script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com https://www.googletagmanager.com;
style-src  'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com;
font-src   'self' https://fonts.gstatic.com;
img-src    'self' data: <dominios de imágenes>;
connect-src 'self' https://www.google-analytics.com https://*.google-analytics.com;
frame-src  https://www.youtube.com https://w.soundcloud.com;
frame-ancestors 'none';
```
- **El matiz honesto (deuda tightenable):** lleva `script-src 'unsafe-inline'`
  porque hay JS inline en el HTML, y `'unsafe-eval'` porque Babel transforma JSX en
  el cliente (usa `eval`/`Function`). Ambos **debilitan** la CSP frente a XSS. Para
  endurecerla: pre-compilar el JSX (quitar Babel del navegador → fuera `'unsafe-eval'`)
  y mover el JS inline a ficheros o firmarlo con **nonces/hashes** por script
  (→ fuera `'unsafe-inline'`). Es la tarea pendiente nº1 de la CSP.
- **Allowlist exacto, no a ojo:** antes de fijar la CSP, lista los recursos REALES
  que carga la página (`<script src>`, `<link href>`, fuentes, analytics, iframes) y
  permite SOLO esos. Una CSP de más rompe la app (pantalla en blanco si bloquea un
  script crítico); de menos no protege.
- **Despliegue seguro de CSP:** en apps complejas, arranca con
  `Content-Security-Policy-Report-Only` (registra violaciones sin bloquear) y pasa a
  enforcing cuando confirmes que no rompe nada. Verifica SIEMPRE en navegador real
  tras desplegar (la consola muestra las violaciones).

**Cómo replicar:** un `SecurityHeadersMiddleware` que ponga las 5-6 cabeceras en
toda respuesta; HSTS solo en https; CSP con allowlist construido a partir de los
recursos reales de la página, asumiendo (y documentando) la deuda de
`unsafe-inline`/`unsafe-eval` si usas inline/Babel, con plan de endurecerla.

---

## 8. Gestión de secretos

**Patrón:**
- **Todo en env vars:** `JWT_SECRET`, `ADMIN_SESSION_SECRET`, `ADMIN_KEY`,
  `DATABASE_URL`, `RESEND_API_KEY`, claves de firma. Cero en el repo.
- **Fallback con warning:** si falta `JWT_SECRET`, genera uno aleatorio al arrancar
  y avisa (no peta, pero deja claro que las sesiones no persisten).
- **`.gitignore`** para logs locales / dumps / cualquier export con secretos.
- **Rotación** documentada para tras un cutover/incidente.

**Cómo replicar:** ninguna credencial en código; lee de env; `.gitignore` agresivo;
si imprimes/logueas, jamás secretos ni hashes.

> Nota operativa: en esta misma sesión, un clasificador BLOQUEÓ un intento de volcar
> el `JWT_SECRET` de producción a la terminal. Es la actitud correcta: **nunca**
> imprimas un secreto de prod, ni siquiera para depurar.

---

## 9. Prevención de abuso y moderación

**Qué protege:** spam, contenido abusivo, gaming del sistema.

**Patrones:**
- **Economía de reciprocidad** (anti-spam estructural): para publicar más, hay que
  haber aportado feedback antes. El abuso se desincentiva por diseño, no solo por
  rate limit.
- **Cuotas** (máx N recursos activos por usuario).
- **Reportar contenido:** endpoint `POST .../reportar` (miembro, no el dueño) que
  **persiste el reporte en DB** (no se pierde si falla el email) **y avisa a los
  moderadores** por email (fire-and-forget). Si abres a desconocidos, sin botón de
  reportar te quedas ciego ante el abuso: la moderación necesita DETECTAR, no solo
  RETIRAR.
- **Moderación:** allowlist de moderadores por env; pueden retirar/editar cualquier
  contenido (camino `_mod` explícito).

**Cómo replicar:** si hay contenido de usuarios → reportar (persistido + aviso) +
moderar (allowlist) + cuota + (si encaja) reciprocidad.

---

## 10. XSS y salida

**Patrón:**
- **El frontend escapa SIEMPRE** el contenido de usuario: `textContent`/una función
  `esc()` en vanilla JS; React escapa por defecto (no usar `dangerouslySetInnerHTML`
  con datos de usuario).
- **Defensa en profundidad pendiente/recomendada:** escapar también en backend
  (`html.escape` en `_sanitize`) por si algún día hay un cliente no-oficial. Hoy el
  riesgo está acotado porque el único cliente escapa, pero es la capa que añadirías
  para no depender del front.

**Cómo replicar:** nunca inyectes HTML con datos de usuario sin escapar; en el
servidor, escapa lo que vaya a un email/HTML que tú generas (los avisos de
comentario/reporte hacen `html.escape` del username/texto).

---

## 11. PII y minimización de datos

- Endpoints públicos: **lista blanca de campos**, nunca email/hash.
- Logs: sin secretos, sin PII innecesaria.
- **GDPR (pendiente de cerrar antes de escalar/cobrar):** borrado de cuenta
  (con `ON DELETE CASCADE` o borrado en cascada manual), export de datos, base
  legal, edad mínima. Si tu proyecto tiene usuarios UE, esto es obligatorio antes
  de cobrar — trátalo como bloqueante, no como "luego".

---

## 12. EL PROCESO (lo más importante — replícalo entero)

Los controles de arriba se ENCONTRARON y se MANTIENEN con este proceso. Es lo que
de verdad evita vulnerabilidades. Cuatro piezas:

### 12.1 Auditoría inicial tipo "V-01..V-10"
Una pasada sistemática enumerando vulnerabilidades con ID, descripción y fix, y se
cierra cada una. (En Mentotrack: CORS abierto→restringido, tokens sin firma→JWT,
dashboard sin auth→cookie admin, sin rate limit→slowapi, passwords de 4→8 chars,
endpoints sin auth→JWT, GET con params sensibles→POST body, etc.) Mantén una TABLA
de vulnerabilidad→fix en el doc del proyecto.

### 12.2 Revisión adversarial multi-agente (el núcleo)
Antes de cada feature sensible o lanzamiento, se corre un **workflow** con esta forma
(probado dos veces esta sesión: revisión del avatar y auditoría pre-lanzamiento):

1. **Fan-out por dimensiones** (en paralelo, lentes independientes y ciegas entre sí):
   subida/validación · servido/path-traversal · autorización/PII · DoS/recursos ·
   (y para lanzamiento: legal/monetización · datos/backups/operación). Cada lente LEE
   EL CÓDIGO REAL y reporta hallazgos con ubicación, severidad y fix.
2. **Verificación adversarial de CADA hallazgo** (escéptico por defecto): un agente
   independiente intenta REFUTAR el hallazgo contra el código; si no puede describir
   una explotación concreta, lo marca **falso positivo**. Esto mata los "genéricos de
   libro" que no aplican.
3. **Síntesis con clasificación de bloqueo:** bloqueante-para-lanzar /
   bloqueante-para-cobrar / pronto / diferible. Decisivo, no salomónico.

Por qué funciona: diversidad de lentes encuentra lo que una sola pasada no ve; la
verificación adversarial filtra el ruido; la clasificación te dice qué frenar de
verdad. **Resultado real:** la revisión del avatar (16 hallazgos→11 reales) encontró
una memory-exhaustion vía header JPEG, DoS por WebP animado y una carrera en username;
la pre-lanzamiento (41→37) encontró el endpoint de audio sin gating y el borrado de
cuenta inexistente. Ninguno era obvio a ojo.

> Plantilla mental del workflow: `parallel(lentes → hallazgos)` →
> `parallel(hallazgos → verificación escéptica)` → `agent(síntesis go/no-go)`.
> Da a cada lente acceso de lectura al repo y pídele ubicación + explotación + fix.

### 12.3 Auditoría pre-lanzamiento con foco de negocio
No solo "¿es seguro?" sino "¿esto nos hipoteca?" (monetización, legal, coste de
almacenamiento, backups). La seguridad incluye no pintarte en una esquina: gatear el
recurso de pago en el ACCESO y no solo en la creación, poder activar/auditar el flag
de pago, política de downgrade, términos de suscripción, etc.

### 12.4 Disciplina de validación y despliegue
Cada cambio, antes de mergear:
- `py_compile` del backend; **transformar el JSX con Babel** y `node --check` de los
  scripts vanilla (cazan errores que romperían la página en blanco).
- **Smoke test contra la DB real** de las funciones nuevas (incluido el caso "no
  existe" → devuelve None/404, confirma que el SQL es válido sin efectos).
- Migraciones con **Alembic**, una cabeza única, **corren en el arranque** del deploy.
- Deploy: trabajar en `dev`, **merge a `main`** (auto-deploy), y **verificar en prod
  tras el deploy**: versión en `/health`, que los endpoints nuevos respondan y estén
  gateados (401/403 sin sesión), que las migraciones corrieron, y **e2e del camino
  feliz** (p. ej. login → pedir recurso firmado → reproducir → 200/206; y sin firma →
  403). No des por buena una corrección de seguridad sin verla viva.

---

## 13. Anti-patrones que evitamos (errores caros)

- **Gatear solo la creación y no el acceso.** (FLAC se gateaba al subir pero el
  endpoint de audio lo servía a cualquiera → el diferenciador de pago se regalaba.)
  Gatea el ACCESO al recurso, no solo su creación.
- **Check-then-act sin atomicidad.** (Comprobar disponibilidad de username y luego
  UPDATE → carrera.) Hazlo atómico en el WHERE o captura la violación de unicidad y
  devuelve 409, no 503.
- **Confiar en extensión/content-type de un upload.** Magic bytes / decoder real /
  re-codificación.
- **Inspeccionar contenido hostil en vez de regenerarlo.** Re-encode > parse.
- **Construir rutas de fichero con input del usuario.** Regex anclada / nombre opaco.
- **Devolver `SELECT *` en endpoints públicos.** Lista blanca de campos.
- **Cap de recursos "infinito por defecto".** Pon límites (tamaño, dimensiones,
  duración, frames, píxeles, cuota) explícitos.
- **Unicidad case-sensitive en identidades.** `LOWER()` único.
- **Imprimir secretos para depurar.** Nunca.
- **Dar por hecho que un fix funciona sin verificarlo en prod.**

---

## 14. Checklist replicable (pégalo en el nuevo proyecto)

**Auth**
- [ ] JWT HS256 con `exp`, verificado con `algorithms=[...]` explícito; secreto en env.
- [ ] bcrypt, min 8 chars; nunca loguear/devolver passwords.
- [ ] Admin: cookie HttpOnly+Secure+SameSite, secreto propio, expiración corta.
- [ ] Helpers de auth en capas (`optional` / `require` / `require_<recurso>`).
- [ ] Username/identidad únicos case-insensitive (`LOWER()`).
- [ ] `token_version` + middleware global para revocar sesiones al cambiar password.

**Autorización**
- [ ] Mutaciones con el dueño en el WHERE (404 si 0 filas).
- [ ] Rol elevado = camino explícito tras check explícito.
- [ ] Endpoints públicos: lista blanca de campos, sin PII.

**Input / inyección**
- [ ] SQL parametrizado siempre; cero concatenación con datos de usuario.
- [ ] `sanitize(text, cap)` central; parseo estricto de IDs/enums.

**Uploads**
- [ ] Allowlist de tipo + cap de tamaño + validación con decoder + re-encode.
- [ ] Límites de dimensión/duración/frames/píxeles; rechazo de animadas.
- [ ] Chequeo de disco + cuota por usuario.

**Media / acceso**
- [ ] Media privada a tags HTML → URL firmada HMAC temporal + `compare_digest`.
- [ ] Media pública → nombre opaco + regex anclada anti path-traversal.

**Transporte / infra**
- [ ] Rate limit por ruta (ajustado al coste); IP real tras proxy.
- [ ] CORS: origins y métodos explícitos, sin comodín con credenciales.
- [ ] **Cabeceras de seguridad** en toda respuesta: nosniff, X-Frame-Options DENY,
  Referrer-Policy, Permissions-Policy, HSTS (solo https), y **CSP** con allowlist real
  (documenta la deuda de `unsafe-inline`/`unsafe-eval` si usas inline/Babel).
- [ ] Secretos solo en env; `.gitignore` agresivo; rotación documentada.

**Abuso / contenido**
- [ ] Reportar (persistido + aviso) + moderar (allowlist) + cuota.
- [ ] Escapado de salida en front; escapar en backend lo que generes (emails/HTML).

**Datos / legal**
- [ ] Borrado de cuenta (cascada) + export + base legal + edad — antes de escalar/cobrar.

**Proceso**
- [ ] Tabla vulnerabilidad→fix mantenida.
- [ ] **Revisión adversarial multi-agente antes de cada lanzamiento/cambio sensible.**
- [ ] Validación pre-merge (compile/transform/smoke) + verificación e2e en prod post-deploy.

---

*Origen: Mentotrack v0.5.63 (jun-2026). Replica los patrones, adapta los idioms,
y corre el proceso del §12 — es lo que de verdad encuentra lo que se te escapa.*
