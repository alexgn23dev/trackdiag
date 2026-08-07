# Entorno de preview en Railway

**No he creado ni modificado nada en Railway.** Esto son los pasos y las
variables; ejecutarlos es decisión tuya.

El código ya está preparado: `backend/entorno.py` decide qué está encendido
según `MENTOTRACK_ENV` y **aborta el arranque** si detecta que un preview
apunta a recursos de producción.

---

## 1. Obtener las huellas de producción

Las huellas son SHA-256 truncados: identifican un secreto sin revelarlo. Se
sacan **una vez**, desde producción, y se pegan como variables del preview.

Con la app de producción arrancada y sesión de admin:

```
GET https://www.mentotrack.com/api/tecnico/versiones
```

En la respuesta, `entorno.huellas`:

```json
{
  "database_url": "a1b2c3d4e5f6a7b8",
  "database_identidad": "9f8e7d6c5b4a3210",
  "jwt_secret": "1122334455667788",
  "resend_api_key": "99aabbccddeeff00"
}
```

Usa **`database_identidad`** (no `database_url`) para `PROD_DB_FINGERPRINT`:
identifica host+puerto+base, así que salta también si alguien crea un usuario
nuevo sobre la misma base de producción. Es el caso peligroso de verdad.

---

## 2. Crear el servicio de preview

En el proyecto `extraordinary-tranquility`:

1. **New → Database → PostgreSQL.** Nómbralo `Postgres-Preview`. Es una
   instancia aparte: nada compartido con la de producción.
2. **New → GitHub Repo → `alexgn23dev/trackdiag`.** Nómbralo
   `Mentotrack-Preview`.
3. En *Settings → Source*, pon la rama a desplegar: `dev`, o la rama de la
   feature que quieras probar. **No pongas `main`.**
4. En *Settings → Networking*, genera un dominio propio
   (`mentotrack-preview.up.railway.app`). No lo enlaces a Cloudflare.
5. Añade un volumen propio en `/data` si quieres paridad; si no, el servicio
   funciona igual (el volumen solo guarda temporales).

---

## 3. Variables del preview

### Obligatorias

| Variable | Valor | Por qué |
|---|---|---|
| `MENTOTRACK_ENV` | `preview` | Enciende toda la protección. Sin esto no hay aislamiento |
| `DATABASE_URL` | `${{Postgres-Preview.DATABASE_URL}}` | Referencia al Postgres **de preview** |
| `PROD_DB_FINGERPRINT` | el `database_identidad` del paso 1 | La app no arranca si la base coincide con producción |
| `JWT_SECRET` | **uno nuevo**, `openssl rand -hex 32` | Un token de preview no debe valer en producción |
| `PROD_JWT_FINGERPRINT` | el `jwt_secret` del paso 1 | Salta si se copió el secreto de producción |
| `ADMIN_KEY` | cualquier cadena distinta | Ídem |

### Servicios externos

En preview vienen **apagados por defecto**: hay que encenderlos a propósito,
no acordarse de apagarlos. Solo defínelas si quieres cambiarlo.

| Variable | Por defecto en preview | Qué apaga |
|---|---|---|
| `EMAIL_ACTIVO` | `0` | Nada de Resend: ni re-enganche, ni encuestas, ni reporte mensual |
| `SHEETS_ACTIVO` | `0` | Nada de espejo a Google Sheets |
| `WEBHOOKS_ACTIVOS` | `0` | Nada de POST a servicios externos |
| `ANALITICA_ACTIVA` | `0` | Sin eventos de analítica |
| `REENGANCHE_ACTIVO` | no definir | El drip queda en dry-run |
| `ENCUESTA_CTA_ACTIVA` | `0` | Sin CTA de encuesta |

**No definas** `RESEND_API_KEY`, `SHEETS_WEBHOOK` ni `ADMIN_EMAIL` en preview.
Si necesitas probar el email de verdad, crea una API key aparte en Resend con
un dominio de pruebas — nunca la de producción, que la app rechaza.

### Opcionales

| Variable | Para qué |
|---|---|
| `PROD_RESEND_FINGERPRINT` | Salta si se pegó la key de Resend de producción |
| `PREVIEW_DB_INTERNA_OK` | `1` para permitir un host `*.railway.internal` (solo si la base de preview también es interna) |
| `PREVIEW_ALLOW_UNSAFE` | `1` para arrancar pese a las alertas. **Romper el cristal**: deja constancia en el log |

---

## 4. Comprobar que quedó aislado

Tras el primer deploy, en los logs del servicio debe aparecer:

```
[ENTORNO] preview: aislamiento verificado · sheets=False email=False webhooks=False analitica=False
```

Si en cambio ves esto, **la app no arrancó a propósito**:

```
ConfiguracionInsegura: El entorno 'preview' apunta a recursos de producción:
  - DATABASE_URL apunta al mismo host/puerto/base que producción
```

Comprobaciones desde fuera:

```bash
# 1. La app se identifica como preview
curl -s https://mentotrack-preview.up.railway.app/api/health
# → {"status":"ok","version":"0.5.71","entorno":"preview"}
#   (producción NO devuelve el campo `entorno`)

# 2. La banda naranja aparece abajo en la web
# 3. Con cookie de admin, el detalle completo:
curl -s https://mentotrack-preview.up.railway.app/api/tecnico/versiones | jq .entorno
# → aislamiento_ok: true, problemas_aislamiento: []
```

---

## 5. Aislamiento de datos y servicios — resumen

| Recurso | Producción | Preview | Cómo se garantiza |
|---|---|---|---|
| Base de datos | `Postgres` | `Postgres-Preview` | Instancia distinta + `PROD_DB_FINGERPRINT` aborta el arranque si coinciden |
| Migraciones | Alembic al arrancar | Alembic al arrancar, **sobre la base de preview** | Sale del `DATABASE_URL` del servicio |
| Almacenamiento | volumen `/data` | volumen propio o temporal | Volumen por servicio en Railway |
| Google Sheets | activo | **apagado** | `SHEETS_ACTIVO=0` por defecto + `SHEETS_WEBHOOK` sin definir |
| Email (Resend) | activo | **apagado** | `EMAIL_ACTIVO=0` + sin `RESEND_API_KEY` + la app rechaza la key de producción |
| Webhooks | activos | **apagados** | `WEBHOOKS_ACTIVOS=0` |
| Analítica | activa | **apagada** | `ANALITICA_ACTIVA=0` |
| Sesiones (JWT) | secreto de producción | secreto propio | `PROD_JWT_FINGERPRINT` salta si se copió |
| Dominio | www.mentotrack.com | `*.up.railway.app` | Sin Cloudflare, sin DNS propio |
| Identificación visual | ninguna | banda naranja fija + `entorno` en `/api/health` | Frontend y backend |

**Lo que sigue siendo manual y conviene revisar cada vez:** que la rama del
servicio de preview no sea `main`, y que el dominio de preview no se enlace
por error a Cloudflare.

---

## 6. Lo que NO cubre esta protección

- **CORS.** `main.py` limita los orígenes a `mentotrack.com`,
  `www.mentotrack.com` y `localhost`. El dominio de preview habrá que
  añadirlo, o el frontend no podrá llamar a su propia API. **Es un cambio en
  producción** (misma lista), así que lo dejo señalado sin tocarlo.
- **Rate limits.** slowapi usa memoria del proceso: preview y producción no se
  interfieren, pero tampoco comparten cupo.
- **El drip de re-enganche.** Si alguien pusiera `REENGANCHE_ACTIVO=1` y una
  `RESEND_API_KEY` válida distinta de la de producción, el preview mandaría
  correos de verdad a los emails que haya **en su propia base**. Con una base
  de preview vacía no hay a quién escribir, pero si se restaura un volcado de
  producción, sí. **Anonimiza los emails si restauras datos reales.**
