# Dashboard Web — I_Site

Dashboard de operaciones para clientes I_Site. Muestra golpes, utilización y baterías de flotas de maquinaria.

**URL pública:** https://dashboard-production-8d92.up.railway.app

---

## Arquitectura

```
dashboard-web/
├── app.py              ← FastAPI backend (lee PostgreSQL o Excel)
├── upload_db.py        ← Sube consolidados Excel → PostgreSQL Railway
├── schema.sql          ← DDL de las tablas golpes y utilizacion
├── requirements.txt
├── railway.toml        ← Config de deploy (startCommand, healthcheck)
└── static/
    ├── index.html      ← Shell HTML con tabs y estructura
    ├── app.js          ← Toda la lógica JS (Chart.js 4.x, fetch, render)
    └── style.css       ← Tema oscuro naranja (#e8650a) y gris (#a0a0a0)
```

---

## Infraestructura

| Pieza | Detalle |
|---|---|
| Hosting | Railway (PaaS) — auto-deploy desde GitHub |
| Repo | https://github.com/NicolasBunster/dashboard |
| Base de datos | PostgreSQL en Railway (1 GB free tier) |
| Deploy | Cada `git push` a `main` redespliega automáticamente (~2 min) |

**Credenciales PostgreSQL (Railway):**
- Public URL: `postgresql://postgres:ODpWLGIDugpiOtGmDYAQRDhJhzNtSmPs@monorail.proxy.rlwy.net:20049/railway`
- Internal URL: `postgresql://postgres:ODpWLGIDugpiOtGmDYAQRDhJhzNtSmPs@postgres.railway.internal:5432/railway`
- Variable de entorno en Railway: `DATABASE_URL` (ya configurada)

---

## Flujo de datos

1. Scripts Playwright descargan Excel desde iSite → carpetas OneDrive por cliente
2. `upload_db.py` lee los consolidados y sube a PostgreSQL (últimos 12 meses)
3. `app.py` sirve los datos desde PostgreSQL (fallback a Excel si no hay DB)
4. El dashboard se actualiza cada 5 minutos automáticamente

**Para subir datos nuevos:**
```bash
# Todos los clientes
set DATABASE_URL=postgresql://postgres:ODpWLGIDugpiOtGmDYAQRDhJhzNtSmPs@monorail.proxy.rlwy.net:20049/railway
python upload_db.py

# Un solo cliente
python upload_db.py --cliente watts
```

---

## Tablas PostgreSQL

**`golpes`** — un registro por golpe de maquinaria
| Columna | Tipo | Descripción |
|---|---|---|
| cliente | VARCHAR | Key del cliente (ej. "watts", "cencosud") |
| maquina | VARCHAR | ID/serie de la máquina |
| nro_flota | VARCHAR | Número de flota |
| familia | VARCHAR | Familia de máquina (CBE, LOW, etc.) |
| modelo / marca | VARCHAR | |
| site | VARCHAR | Bodega/planta |
| conductor | VARCHAR | Nombre del operador |
| nivel | VARCHAR | "Golpe Altos", "Medios", "Bajos" |
| hora_golpe | VARCHAR | Fecha/hora como string (dd/mm/yyyy HH:MM:SS) |
| descarga_bateria | FLOAT | |
| velocidad | FLOAT | |

**`utilizacion`** — un registro por sesión de uso (llave ON→OFF)
| Columna | Tipo | Descripción |
|---|---|---|
| cliente | VARCHAR | |
| maquina / nro_flota / familia / modelo / marca / site / conductor | VARCHAR | |
| inicio | VARCHAR | Fecha/hora inicio sesión |
| seg_llave | FLOAT | Segundos con llave encendida |
| seg_funcionam | FLOAT | Segundos en funcionamiento |
| seg_traccion | FLOAT | Segundos en tracción |
| seg_elevacion | FLOAT | Segundos en elevación |
| ratio_func_llave | FLOAT | Eficiencia (func/llave) |
| metodo_apagado | VARCHAR | "Normal", "Autoapagado por Inactividad", "Batería Desconectada" |
| claves_compartidas | INTEGER | Cantidad de operadores distintos en esa sesión |

> **Nota:** Las fechas se guardan como VARCHAR para evitar problemas de DateStyle en PostgreSQL. Al leerlas en pandas, usar `pd.to_datetime(..., dayfirst=True, errors="coerce")`.

> **Nota:** El nivel en golpes tiene formato "Golpe Altos"/"Medios"/"Bajos", no "Altos" solamente. Usar `.str.contains("altos", na=False)` para filtrar.

---

## API endpoints

```
GET /                           → Redirige a index.html
GET /dashboard/{cliente}        → Redirige a index.html
GET /health                     → {"status":"ok","db":true/false}
GET /api/clientes               → Lista todos los clientes con flags golpes/util/bat
GET /api/dashboard/{cliente}    → Datos del dashboard

  Parámetros opcionales:
    modulo=golpes|util|bat      (lazy load — omitir para todos)
    desde=YYYY-MM-DD
    hasta=YYYY-MM-DD
    familia=...
    site=...
    conductor=...
```

---

## Frontend

- **Tabs:** GOLPES / UTILIZACIÓN / BATERÍAS / RANKINGS
- **Lazy loading:** cada tab solo carga su módulo. RANKINGS carga los 3 a la vez.
- **Auto-refresh:** cada 5 minutos recarga el módulo activo
- **Filtros:** fecha desde/hasta, familia, site, conductor (top de la página)
- **Colores:** naranja `#e8650a` (accent), gris `#a0a0a0` (secondary)
- **Charts:** Chart.js 4.4 — donut, línea, barras, barras horizontales, tablas ranking

### Estructura de `app.js`

| Función | Qué hace |
|---|---|
| `cargarModulo()` | Fetch `/api/dashboard/{cliente}?modulo=...` y renderiza |
| `renderGolpes(g)` | KPIs + donut familia + línea mes + barras 30 días + ranking |
| `renderUtil(u)` | KPIs + donut horas + barras claves + línea mes + ranking |
| `renderBat(b)` | Barras apagado máquina/conductor + mes + hora + ranking |
| `renderRankings(d)` | 4 tablas: golpes altos, bat desc, claves compartidas, hrs utilización |
| `showTab(name, btn)` | Cambia tab, dispara carga lazy si cambió el módulo |

---

## Clientes disponibles

Los clientes están definidos en `CLIENTES` dict dentro de `app.py` y en `upload_db.py`. Key en minúsculas (ej. `watts`, `cencosud`, `agrosuper`). El dashboard los lista automáticamente en el selector.

---

## Cómo modificar y publicar

```bash
# 1. Editar los archivos necesarios
#    app.py       → lógica backend / endpoints / procesamiento
#    static/app.js → lógica frontend / charts
#    static/index.html → estructura HTML
#    static/style.css  → estilos

# 2. Commit y push (Railway redespliega solo)
cd "...dashboard-web"
git add app.py static/app.js static/index.html static/style.css
git commit -m "descripción del cambio"
git push

# 3. En ~2 minutos el cambio está live en:
#    https://dashboard-production-8d92.up.railway.app
```
