# Estudio histórico de Mentotrack — scripts

Scripts que producen todas las cifras de `estudio-historico-mentotrack.md`
(raíz del repo). Para reejecutar el estudio con datos actualizados:

```bash
cd backend/scripts/estudio_historico
python3 01_extraer.py    # Postgres (Railway) → estudio.db local (gitignored)
python3 02_estudio.py    # imprime todo el análisis por secciones §0-§7
```

Requisitos: `railway` CLI logueado y linkado al proyecto (para obtener
`DATABASE_PUBLIC_URL` sin exponerla) y `psycopg2`. El resto es stdlib.

- `estudio.db` contiene emails de usuarios → está gitignored y no debe salir
  de la máquina local.
- Cada sección impresa (§0 higiene, §1 diagnósticos, §2 co-ocurrencia,
  §3 métricas, §4 evolución, §5 brecha, §6 uso, §7 contraintuitivos) se
  referencia desde el markdown del estudio.
- Ojo al confound de §4: el motor cambió de versión durante el histórico
  (hipótesis añadidas/gateadas), así que la evolución de diagnósticos NO es
  evolución de los usuarios.
