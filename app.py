"""
Dashboard Web I_Site — FastAPI backend
Uso local : python app.py          (lee desde Excel en OneDrive)
Uso Railway: DATABASE_URL=... python app.py  (lee desde PostgreSQL)
"""
import os
import time
import math
from pathlib import Path
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional

import secrets
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# ── Autenticación admin ───────────────────────────────────────────────────────
# Configura ADMIN_USER y ADMIN_PASSWORD como variables de entorno en Railway.
# Si no están definidas, el admin queda deshabilitado (solo existen URLs de cliente).
_security = HTTPBasic(auto_error=False)

def _verificar_admin(creds: HTTPBasicCredentials = Depends(_security)):
    user = os.getenv("ADMIN_USER", "")
    pwd  = os.getenv("ADMIN_PASSWORD", "")
    if not user or not pwd:
        raise HTTPException(403, "Admin no configurado")
    ok = (
        creds is not None
        and secrets.compare_digest(creds.username.encode(), user.encode())
        and secrets.compare_digest(creds.password.encode(), pwd.encode())
    )
    if not ok:
        raise HTTPException(
            401, "Credenciales incorrectas",
            headers={"WWW-Authenticate": "Basic realm='I_Site Admin'"}
        )

# ── PostgreSQL (opcional) ─────────────────────────────────────────────────────
_db_engine = None

def _get_db():
    global _db_engine
    if _db_engine is not None:
        return _db_engine
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        return None
    try:
        from sqlalchemy import create_engine
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        _db_engine = create_engine(db_url, pool_pre_ping=True)
        print("  Modo: PostgreSQL (Railway)")
        return _db_engine
    except Exception as e:
        print(f"  [DB] No se pudo conectar: {e}")
        return None

# ── Paths ─────────────────────────────────────────────────────────────────────

def _base():
    onedrive = Path(os.path.expanduser("~")) / "OneDrive - Arrendamiento de Maquinaria SPA" / "I_SITE - Documentos"
    legacy   = Path(r"C:\Users\Notebook\Arrendamiento de Maquinaria SPA\I_SITE - Documentos")
    return onedrive if onedrive.exists() else legacy

BASE = _base()

# Mapa cliente → carpetas de datos
CLIENTES = {
    "cencosud":     {"label": "CENCOSUD",            "golpes": BASE/"CENCOSUD/Dashboard - Cencosud/Golpes Cencosud",           "util": BASE/"CENCOSUD/Dashboard - Cencosud/Utilización Cencosud",       "bat": BASE/"CENCOSUD/Dashboard - Cencosud/Baterías Cencosud"},
    "agrosuper":    {"label": "AGROSUPER",            "golpes": BASE/"AGROSUPER/Dashboard - Agrosuper/Golpes Agrosuper",         "util": BASE/"AGROSUPER/Dashboard - Agrosuper/Utilización Agrosuper",     "bat": BASE/"AGROSUPER/Dashboard - Agrosuper/Baterías Agrosuper"},
    "watts":        {"label": "WATT'S",               "golpes": BASE/"WATT'S/Dashboard - Watts/Golpes Watts",                   "util": BASE/"WATT'S/Dashboard - Watts/Utilización Watts",               "bat": None},
    "adidas":       {"label": "Adidas",               "golpes": BASE/"Adidas/Golpes Adidas",                                    "util": BASE/"Adidas/Utilización Adidas",                                 "bat": None},
    "agrocommerce": {"label": "Agrocommerce",         "golpes": BASE/"Agrocommerce/Golpes Agrocommerce",                        "util": BASE/"Agrocommerce/Utilización Agrocommerce",                     "bat": None},
    "arcor":        {"label": "Arcor",                "golpes": BASE/"Arcor/Golpes Arcor",                                      "util": BASE/"Arcor/Utilización Arcor",                                   "bat": None},
    "ariztia":      {"label": "Ariztia",              "golpes": BASE/"Ariztia/Golpes Ariztia",                                  "util": BASE/"Ariztia/Utilización Ariztia",                               "bat": None},
    "ascend":       {"label": "Ascend",               "golpes": BASE/"Ascend Laboratories SpA/Golpes Ascend",                   "util": BASE/"Ascend Laboratories SpA/Utilización Ascend",               "bat": None},
    "bomi":         {"label": "Bomi Group",           "golpes": BASE/"Bomi Group/Golpes Bomi",                                  "util": BASE/"Bomi Group/Utilización Bomi",                               "bat": None},
    "ccu":          {"label": "CCU",                  "golpes": BASE/"CCU/Golpes CCU",                                          "util": BASE/"CCU/Utilización CCU",                                       "bat": None},
    "cmf":          {"label": "CMF",                  "golpes": BASE/"CMF/Golpes CMF",                                          "util": BASE/"CMF/Utilización CMF",                                       "bat": None},
    "comaco":       {"label": "COMACO",               "golpes": BASE/"COMACO/Golpes COMACO",                                    "util": BASE/"COMACO/Utilización COMACO",                                 "bat": None},
    "caribean":     {"label": "Caribean Pharma",      "golpes": BASE/"Caribean Pharma/Golpes Caribean Pharma",                  "util": BASE/"Caribean Pharma/Utilización Caribean Pharma",               "bat": None},
    "chilecargo":   {"label": "ChileCargo",           "golpes": BASE/"ChileCargo/Golpes ChileCargo",                            "util": BASE/"ChileCargo/Utilización ChileCargo",                         "bat": None},
    "cial":         {"label": "Cial Alimentos",       "golpes": BASE/"Cial Alimentos/Golpes Cial Alimentos",                    "util": BASE/"Cial Alimentos/Utilización Cial Alimentos",                 "bat": None},
    "embonor":      {"label": "Coca Cola Embonor",    "golpes": BASE/"Coca Cola Embonor/Golpes Embonor",                        "util": BASE/"Coca Cola Embonor/Utilización Embonor",                     "bat": None},
    "cristalerias": {"label": "Cristalerías Toro",    "golpes": BASE/"Cristalerías Toro/Golpes Cristalerias Toro",              "util": BASE/"Cristalerías Toro/Utilización Cristalerias Toro",           "bat": None},
    "din":          {"label": "DIN S.A.",             "golpes": BASE/"DIN S.A./Golpes DIN",                                     "util": BASE/"DIN S.A./Utilización DIN",                                  "bat": None},
    "dragpharma":   {"label": "Dragpharma",           "golpes": BASE/"Laboratorio Dragpharma/Golpes Dragpharma",                "util": BASE/"Laboratorio Dragpharma/Utilización Dragpharma",             "bat": None},
    "egakat":       {"label": "EGAKAT",               "golpes": BASE/"EGAKAT/Golpes Egakat",                                    "util": BASE/"EGAKAT/Utilización Egakat",                                 "bat": None},
    "fedex":        {"label": "Fedex",                "golpes": BASE/"Fedex/Golpes Fedex",                                      "util": BASE/"Fedex/Utilización Fedex",                                   "bat": None},
    "friofort":     {"label": "FRIOFORT",             "golpes": BASE/"FRIOFORT/Golpes Friofort",                                "util": BASE/"FRIOFORT/Utilización Friofort",                             "bat": None},
    "hoffens":      {"label": "Hoffens",              "golpes": BASE/"Hoffens/Golpes Hoffens",                                  "util": BASE/"Hoffens/Utilización Hoffens",                               "bat": None},
    "icb":          {"label": "ICB S.A.",             "golpes": BASE/"ICB S.A./Golpes ICB",                                     "util": BASE/"ICB S.A./Utilización ICB",                                  "bat": None},
    "imicar":       {"label": "IMICAR",               "golpes": BASE/"IMICAR/Golpes IMICAR",                                    "util": BASE/"IMICAR/Utilización IMICAR",                                 "bat": None},
    "imega":        {"label": "Imega Ventus",         "golpes": BASE/"Imega Ventus/Golpes Imega Ventus",                        "util": BASE/"Imega Ventus/Utilización Imega Ventus",                     "bat": None},
    "imperial":     {"label": "Imperial",             "golpes": BASE/"Imperial/Golpes Imperial",                                "util": BASE/"Imperial/Utilización Imperial",                             "bat": None},
    "intcomex":     {"label": "Intcomex",             "golpes": BASE/"Intcomex/Golpes Intcomex",                                "util": BASE/"Intcomex/Utilización Intcomex",                             "bat": None},
    "int-paper":    {"label": "Internacional Paper",  "golpes": BASE/"Internacional Paper/Golpes Internacional Paper",          "util": BASE/"Internacional Paper/Utilización Internacional Paper",       "bat": None},
    "keylogistics": {"label": "Keylogistics",         "golpes": BASE/"Keylogistics/Golpes Keylogistics",                        "util": BASE/"Keylogistics/Utilización Keylogistics",                     "bat": None},
    "kuehne":       {"label": "Kuehne + Nagel",       "golpes": BASE/"Kuehne + Nagel/Golpes Kuehne Nagel",                      "util": BASE/"Kuehne + Nagel/Utilización Kuehne Nagel",                   "bat": None},
    "colun":        {"label": "Colun",                "golpes": BASE/"Colun/Golpes Colun",                                      "util": BASE/"Colun/Utilización Colun",                                   "bat": None},
    "lapolar":      {"label": "Empresas La Polar",    "golpes": BASE/"Empresas La Polar/Golpes La Polar",                       "util": BASE/"Empresas La Polar/Utilización La Polar",                    "bat": None},
    "loreal":       {"label": "L'OREAL",              "golpes": BASE/"L'OREAL/Golpes LOREAL",                                   "util": BASE/"L'OREAL/Utilización LOREAL",                                "bat": None},
    "logisfashion": {"label": "Logisfashion",         "golpes": BASE/"Logisfashion/Golpes Logisfashion",                        "util": BASE/"Logisfashion/Utilización Logisfashion",                     "bat": None},
    "nestle":       {"label": "Nestlé",               "golpes": BASE/"Nestlé/Golpes Nestle",                                    "util": BASE/"Nestlé/Utilización Nestle",                                 "bat": None},
    "prisa":        {"label": "PRISA",                "golpes": BASE/"PRISA/Golpes PRISA",                                      "util": BASE/"PRISA/Utilización PRISA",                                   "bat": None},
    "puma":         {"label": "PUMA",                 "golpes": BASE/"PUMA/Golpes PUMA",                                        "util": BASE/"PUMA/Utilización PUMA",                                     "bat": None},
    "quelen":       {"label": "Quelen Export",        "golpes": BASE/"Quelen Export/Golpes Quelen Export",                      "util": BASE/"Quelen Export/Utilización Quelen Export",                   "bat": None},
    "recilar":      {"label": "Re-cilar",             "golpes": BASE/"Re-cilar/Golpes Re-ciclar",                               "util": BASE/"Re-cilar/Utilización Re-ciclar",                            "bat": None},
    "rosen":        {"label": "ROSEN",                "golpes": BASE/"ROSEN/Golpes ROSEN",                                      "util": BASE/"ROSEN/Utilización ROSEN",                                   "bat": None},
    "sherwin":      {"label": "Sherwin Williams",     "golpes": BASE/"Sherwin Williams/Golpes Sherwin Williams",                "util": BASE/"Sherwin Williams/Utilización Sherwin Williams",             "bat": None},
    "smu":          {"label": "SMU",                  "golpes": BASE/"SMU/Golpes SMU",                                          "util": BASE/"SMU/Utilización SMU",                                       "bat": None},
    "tecnored":     {"label": "TecnoRed",             "golpes": BASE/"TecnoRed/Golpes TecnoRed",                                "util": BASE/"TecnoRed/Utilización TecnoRed",                             "bat": None},
    "tottus":       {"label": "Tottus",               "golpes": BASE/"Tottus/Golpes Tottus",                                    "util": BASE/"Tottus/Utilización Tottus",                                 "bat": None},
    "unilever":     {"label": "Unilever",             "golpes": BASE/"Unilever/Golpes Unilever",                                "util": BASE/"Unilever/Utilización Unilever",                             "bat": None},
}

# ── Cache ─────────────────────────────────────────────────────────────────────

_cache: dict = {}
CACHE_TTL = 300  # 5 minutos

def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except:
        return 0.0

def _cache_key(cliente: str, carpeta: Path) -> str:
    return f"{cliente}_{carpeta.name}"

def _get_cached(key: str, path: Path):
    if key in _cache:
        entry = _cache[key]
        if time.time() - entry["ts"] < CACHE_TTL and _mtime(path) <= entry["mtime"]:
            return entry["df"]
    return None

def _set_cached(key: str, path: Path, df):
    _cache[key] = {"df": df, "ts": time.time(), "mtime": _mtime(path)}

# ── Lectores de Excel ─────────────────────────────────────────────────────────

def _leer_archivo(path: Path) -> pd.DataFrame:
    """Lee un Excel con engine openpyxl y normaliza columnas."""
    df = pd.read_excel(path, engine="openpyxl")
    df.columns = df.columns.str.strip()
    return df

def _leer_excel_consolidado(carpeta: Path, nombre_base: str, prefix: str) -> Optional[pd.DataFrame]:
    """Lee _NOMBRE.xlsx o combina _NOMBRE_parte[0-9].xlsx (excluye _pivot)."""
    if carpeta is None:
        return None
    try:
        # Archivo único
        f_unico = carpeta / f"{nombre_base}.xlsx"
        if f_unico.exists():
            key = _cache_key(prefix, f_unico)
            cached = _get_cached(key, f_unico)
            if cached is not None:
                return cached
            df = _leer_archivo(f_unico)
            _set_cached(key, f_unico, df)
            return df
        # Partes numeradas: _parte1.xlsx, _parte2.xlsx — excluye _pivot y similares
        partes = sorted(p for p in carpeta.glob(f"{nombre_base}_parte*.xlsx")
                        if p.stem.split("_parte")[-1].isdigit())
        if not partes:
            return None
        key = _cache_key(prefix, partes[-1])
        mtime_max = max(_mtime(p) for p in partes)
        if key in _cache:
            entry = _cache[key]
            if time.time() - entry["ts"] < CACHE_TTL and mtime_max <= entry["mtime"]:
                return entry["df"]
        df = pd.concat([_leer_archivo(p) for p in partes], ignore_index=True)
        _cache[key] = {"df": df, "ts": time.time(), "mtime": mtime_max}
        return df
    except Exception as e:
        print(f"[ERROR] _leer_excel_consolidado({carpeta.name}, {nombre_base}): {e}")
        return None

def _leer_desde_db(tabla: str, cliente: str) -> Optional[pd.DataFrame]:
    engine = _get_db()
    if engine is None:
        return None
    key = f"db_{tabla}_{cliente}"
    if key in _cache:
        entry = _cache[key]
        if time.time() - entry["ts"] < CACHE_TTL:
            return entry["df"]
    try:
        df = pd.read_sql(f"SELECT * FROM {tabla} WHERE cliente = %(c)s", engine, params={"c": cliente})
        if len(df) == 0:
            return None
        df = df.drop(columns=["id", "cliente"], errors="ignore")
        _cache[key] = {"df": df, "ts": time.time(), "mtime": 0}
        return df
    except Exception as e:
        print(f"  [DB] Error leyendo {tabla}/{cliente}: {e}")
        return None

def _leer_consolidado_golpes(carpeta: Path, cliente: str = None) -> Optional[pd.DataFrame]:
    df = _leer_desde_db("golpes", cliente) if cliente else None
    return df if df is not None else _leer_excel_consolidado(carpeta, "_CONSOLIDADO_GOLPES", "g")

def _leer_consolidado_util(carpeta: Path, cliente: str = None) -> Optional[pd.DataFrame]:
    df = _leer_desde_db("utilizacion", cliente) if cliente else None
    return df if df is not None else _leer_excel_consolidado(carpeta, "_CONSOLIDADO_UTILIZACION", "u")

def _leer_consolidado_bat(carpeta: Path, cliente: str = None) -> Optional[pd.DataFrame]:
    # Baterías usa la tabla utilizacion filtrada por método de apagado
    df = _leer_desde_db("utilizacion", cliente) if cliente else None
    return df if df is not None else _leer_excel_consolidado(carpeta, "_CONSOLIDADO_BATERIAS", "b")

# ── Procesado de Golpes ───────────────────────────────────────────────────────

def _procesar_golpes(df: pd.DataFrame, fecha_desde=None, fecha_hasta=None,
                     familia=None, site=None, conductor=None) -> dict:
    # Normalizar columna de fecha
    col_fecha = next((c for c in df.columns if "hora" in c.lower() or "fecha" in c.lower()), None)
    col_nivel = next((c for c in df.columns if "nivel" in c.lower()), None)
    col_familia = next((c for c in df.columns if "familia" in c.lower()), None)
    col_site = next((c for c in df.columns if c.lower() == "site"), None)
    col_conductor = next((c for c in df.columns if "conductor" in c.lower()), None)
    col_maquina = next((c for c in df.columns if "máquina" in c.lower() or "maquina" in c.lower()), None)
    col_bat = next((c for c in df.columns if "descarga" in c.lower() or "batería" in c.lower()), None)

    # Parsear fecha
    if col_fecha:
        df = df.copy()
        df["__fecha"] = pd.to_datetime(df[col_fecha], errors="coerce", dayfirst=True)
        if fecha_desde:
            df = df[df["__fecha"] >= pd.to_datetime(fecha_desde)]
        if fecha_hasta:
            df = df[df["__fecha"] <= pd.to_datetime(fecha_hasta) + timedelta(days=1)]

    # Filtros adicionales
    if familia and col_familia:
        df = df[df[col_familia].astype(str).str.contains(familia, case=False, na=False)]
    if site and col_site:
        df = df[df[col_site].astype(str).str.contains(site, case=False, na=False)]
    if conductor and col_conductor:
        df = df[df[col_conductor].astype(str).str.contains(conductor, case=False, na=False)]

    total = len(df)
    if total == 0:
        return {"kpis": {}, "por_familia": [], "por_mes": [], "ultimos_30dias": [], "ranking": [], "sites": [], "familias": [], "conductores": []}

    # KPIs
    altos  = int((df[col_nivel].str.lower().str.contains("altos", na=False)).sum()) if col_nivel else 0
    medios = int((df[col_nivel].str.lower().str.contains("medios", na=False)).sum()) if col_nivel else 0
    n_conductores = int(df[col_conductor].nunique()) if col_conductor else 0
    n_maquinas    = int(df[col_maquina].nunique()) if col_maquina else 0
    bat_desc = int(df[col_bat].sum()) if col_bat else 0

    # Por familia (para donut)
    por_familia = []
    if col_familia and col_nivel:
        gf = df[df[col_nivel].str.lower().str.contains("altos", na=False)].groupby(col_familia).size().reset_index(name="total")
        por_familia = [{"familia": r[col_familia], "total": int(r["total"])} for _, r in gf.iterrows()]

    # Por mes (línea)
    por_mes = []
    if col_fecha and col_nivel:
        dm = df[df[col_nivel].str.lower().str.contains("altos", na=False)].copy()
        dm["mes"] = dm["__fecha"].dt.to_period("M").astype(str)
        gm = dm.groupby("mes").size().reset_index(name="total").sort_values("mes")
        por_mes = [{"mes": r["mes"], "total": int(r["total"])} for _, r in gm.iterrows()]

    # Últimos 30 días (barras)
    ultimos_30 = []
    if col_fecha and col_nivel:
        hoy = datetime.now()
        d30 = df[(df["__fecha"] >= hoy - timedelta(days=30)) & (df[col_nivel].str.lower().str.contains("altos", na=False))].copy()
        d30["dia"] = d30["__fecha"].dt.day
        gd = d30.groupby("dia").size().reset_index(name="total").sort_values("dia")
        ultimos_30 = [{"dia": int(r["dia"]), "total": int(r["total"])} for _, r in gd.iterrows()]

    # Ranking conductores por golpes altos
    ranking = []
    if col_conductor and col_nivel:
        ra = df[df[col_nivel].str.lower().str.contains("altos", na=False)].groupby(col_conductor).size().reset_index(name="golpes_altos")
        ra = ra.sort_values("golpes_altos", ascending=False).head(50)
        ranking = [{"conductor": r[col_conductor], "golpes_altos": int(r["golpes_altos"])} for _, r in ra.iterrows()]

    # Filtros disponibles
    sites_disp = sorted(df[col_site].dropna().unique().tolist()) if col_site else []
    fam_disp   = sorted(df[col_familia].dropna().unique().tolist()) if col_familia else []
    cond_disp  = sorted(df[col_conductor].dropna().unique().tolist()) if col_conductor else []

    return {
        "kpis": {
            "total_conductores": n_conductores,
            "total_golpes_altos": altos,
            "total_golpes_medios": medios,
            "total_maquinas": n_maquinas,
            "apagado_bat_desc": bat_desc,
        },
        "por_familia": por_familia,
        "por_mes": por_mes,
        "ultimos_30dias": ultimos_30,
        "ranking": ranking,
        "sites": sites_disp,
        "familias": fam_disp,
        "conductores": cond_disp,
    }

# ── Procesado de Utilización ──────────────────────────────────────────────────

def _procesar_util(df: pd.DataFrame, fecha_desde=None, fecha_hasta=None,
                   familia=None, site=None, conductor=None) -> dict:
    col_inicio   = next((c for c in df.columns if "inicio" in c.lower()), None)
    col_familia  = next((c for c in df.columns if "familia" in c.lower()), None)
    col_site     = next((c for c in df.columns if c.lower() == "site"), None)
    col_conductor= next((c for c in df.columns if "conductor" in c.lower()), None)
    col_seg_func = next((c for c in df.columns if "funcionam" in c.lower()), None)
    col_seg_llave= next((c for c in df.columns if "llave" in c.lower() and "seg" in c.lower()), None)
    col_metodo   = next((c for c in df.columns if "método" in c.lower() or "metodo" in c.lower()), None)
    col_claves   = next((c for c in df.columns if "clave" in c.lower() and "compartida" in c.lower()), None)

    if col_inicio:
        df = df.copy()
        df["__fecha"] = pd.to_datetime(df[col_inicio], errors="coerce", dayfirst=True)
        if fecha_desde:
            df = df[df["__fecha"] >= pd.to_datetime(fecha_desde)]
        if fecha_hasta:
            df = df[df["__fecha"] <= pd.to_datetime(fecha_hasta) + timedelta(days=1)]

    if familia and col_familia:
        df = df[df[col_familia].astype(str).str.contains(familia, case=False, na=False)]
    if site and col_site:
        df = df[df[col_site].astype(str).str.contains(site, case=False, na=False)]
    if conductor and col_conductor:
        df = df[df[col_conductor].astype(str).str.contains(conductor, case=False, na=False)]

    if len(df) == 0:
        return {"kpis": {}, "hrs_familia": [], "claves_conductor": [], "hrs_mes": [], "hrs_dia": [], "ranking": [], "sites": [], "familias": [], "conductores": []}

    hrs_func  = float(df[col_seg_func].sum() / 3600)  if col_seg_func  else 0
    hrs_llave = float(df[col_seg_llave].sum() / 3600) if col_seg_llave else 0
    eficiencia = round(hrs_func / hrs_llave * 100, 1) if hrs_llave else 0
    apagado_bat = int((df[col_metodo].str.lower().str.contains("batería|bateria", na=False)).sum()) if col_metodo else 0

    # Horas func por familia
    hrs_familia = []
    if col_familia and col_seg_func:
        gf = df.groupby(col_familia)[col_seg_func].sum() / 3600
        hrs_familia = [{"familia": k, "horas": round(v, 1)} for k, v in gf.items()]

    # Claves compartidas por conductor
    claves_conductor = []
    if col_conductor and col_claves:
        gc = df.groupby(col_conductor)[col_claves].sum().sort_values(ascending=False).head(50)
        claves_conductor = [{"conductor": k, "claves": int(v)} for k, v in gc.items() if v > 0]

    # Hrs func por mes
    hrs_mes = []
    if col_inicio and col_seg_func:
        dm = df.copy()
        dm["mes"] = dm["__fecha"].dt.to_period("M").astype(str)
        gm = dm.groupby("mes")[col_seg_func].sum() / 3600
        hrs_mes = [{"mes": k, "horas": round(v, 1)} for k, v in sorted(gm.items())]

    # Hrs func por día (últimos 30 días)
    hrs_dia = []
    if col_inicio and col_seg_func:
        hoy = datetime.now()
        dd = df[df["__fecha"] >= hoy - timedelta(days=30)].copy()
        dd["dia"] = dd["__fecha"].dt.day
        gd = dd.groupby("dia")[col_seg_func].sum() / 3600
        hrs_dia = [{"dia": int(k), "horas": round(v, 1)} for k, v in sorted(gd.items())]

    # Ranking por eficiencia (mayor a menor)
    ranking = []
    if col_conductor and col_seg_func and col_seg_llave:
        rk = df.groupby(col_conductor).agg(
            func=pd.NamedAgg(col_seg_func, "sum"),
            llave=pd.NamedAgg(col_seg_llave, "sum"),
        ).reset_index()
        rk["eficiencia"] = (rk["func"] / rk["llave"] * 100).round(1)
        rk = rk.sort_values("eficiencia", ascending=False).head(50)
        ranking = [{"conductor": r[col_conductor], "eficiencia": float(r["eficiencia"]),
                    "hrs_func": round(r["func"]/3600, 1)} for _, r in rk.iterrows()]

    # Ranking horas utilización (menor a mayor — peor rendimiento primero)
    ranking_hrs = []
    if col_conductor and col_seg_func:
        rh = df.groupby(col_conductor)[col_seg_func].sum().reset_index()
        rh = rh.rename(columns={col_seg_func: "seg_func"})
        rh["hrs_func"] = (rh["seg_func"] / 3600).round(1)
        rh = rh.sort_values("hrs_func", ascending=True).head(50)
        ranking_hrs = [{"conductor": r[col_conductor], "hrs_func": float(r["hrs_func"])} for _, r in rh.iterrows()]

    sites_disp = sorted(df[col_site].dropna().unique().tolist()) if col_site else []
    fam_disp   = sorted(df[col_familia].dropna().unique().tolist()) if col_familia else []
    cond_disp  = sorted(df[col_conductor].dropna().unique().tolist()) if col_conductor else []

    return {
        "kpis": {
            "hrs_funcionamiento": round(hrs_func, 0),
            "hrs_llave": round(hrs_llave, 0),
            "pct_eficiencia": eficiencia,
            "apagado_bat_desc": apagado_bat,
        },
        "hrs_familia": hrs_familia,
        "claves_conductor": claves_conductor,
        "hrs_mes": hrs_mes,
        "hrs_dia": hrs_dia,
        "ranking": ranking,
        "ranking_hrs": ranking_hrs,
        "sites": sites_disp,
        "familias": fam_disp,
        "conductores": cond_disp,
    }

# ── Procesado de Baterías ─────────────────────────────────────────────────────

def _procesar_bat(df: pd.DataFrame, fecha_desde=None, fecha_hasta=None,
                  conductor=None) -> dict:
    col_inicio   = next((c for c in df.columns if "inicio" in c.lower()), None)
    col_conductor= next((c for c in df.columns if "conductor" in c.lower()), None)
    col_maquina  = next((c for c in df.columns if "máquina" in c.lower() or "maquina" in c.lower()), None)
    col_metodo   = next((c for c in df.columns if "método" in c.lower() or "metodo" in c.lower()), None)
    col_pct_fin  = next((c for c in df.columns if "fin" in c.lower() and "%" in c), None)

    if col_inicio:
        df = df.copy()
        df["__fecha"] = pd.to_datetime(df[col_inicio], errors="coerce", dayfirst=True)
        if fecha_desde:
            df = df[df["__fecha"] >= pd.to_datetime(fecha_desde)]
        if fecha_hasta:
            df = df[df["__fecha"] <= pd.to_datetime(fecha_hasta) + timedelta(days=1)]

    if conductor and col_conductor:
        df = df[df[col_conductor].astype(str).str.contains(conductor, case=False, na=False)]

    if len(df) == 0:
        return {"apagado_maquina": [], "apagado_conductor": [], "por_mes": [], "por_hora": [], "incidentes_20pct": [], "ranking": [], "conductores": []}

    def _metodo_label(m):
        m = str(m).lower()
        if "batería" in m or "desconect" in m:
            return "Batería Desconectada"
        if "inactividad" in m:
            return "Inactividad"
        return "Normal"

    if col_metodo:
        df = df.copy()
        df["__metodo"] = df[col_metodo].apply(_metodo_label)

    # Apagado por máquina
    apagado_maquina = []
    if col_maquina and col_metodo:
        gm = df.groupby([col_maquina, "__metodo"]).size().unstack(fill_value=0).reset_index()
        for _, r in gm.head(20).iterrows():
            apagado_maquina.append({
                "maquina": str(r[col_maquina]),
                "normal": int(r.get("Normal", 0)),
                "bat_desc": int(r.get("Batería Desconectada", 0)),
                "inactividad": int(r.get("Inactividad", 0)),
            })

    # Apagado por conductor
    apagado_conductor = []
    if col_conductor and col_metodo:
        gc = df.groupby([col_conductor, "__metodo"]).size().unstack(fill_value=0).reset_index()
        for _, r in gc.head(20).iterrows():
            apagado_conductor.append({
                "conductor": str(r[col_conductor]),
                "normal": int(r.get("Normal", 0)),
                "bat_desc": int(r.get("Batería Desconectada", 0)),
            })

    # Por mes
    por_mes = []
    if col_inicio:
        df["mes"] = df["__fecha"].dt.to_period("M").astype(str)
        gm2 = df.groupby("mes").size().reset_index(name="total").sort_values("mes")
        por_mes = [{"mes": r["mes"], "total": int(r["total"])} for _, r in gm2.iterrows()]

    # Por hora (últimos 6 meses)
    por_hora = []
    if col_inicio:
        d6m = df[df["__fecha"] >= datetime.now() - timedelta(days=180)].copy()
        d6m["hora"] = d6m["__fecha"].dt.hour
        gh = d6m.groupby("hora").size().reset_index(name="total").sort_values("hora")
        por_hora = [{"hora": int(r["hora"]), "total": int(r["total"])} for _, r in gh.iterrows()]

    # Incidentes batería <20%
    incidentes_20 = []
    if col_pct_fin and col_inicio:
        d_bajo = df[pd.to_numeric(df[col_pct_fin], errors="coerce") < 20].copy()
        d_bajo["mes"] = d_bajo["__fecha"].dt.to_period("M").astype(str)
        gi = d_bajo.groupby("mes").size().reset_index(name="total").sort_values("mes")
        incidentes_20 = [{"mes": r["mes"], "total": int(r["total"])} for _, r in gi.iterrows()]

    # Ranking por % batería desconectada
    ranking = []
    if col_conductor and col_metodo:
        total_c = df.groupby(col_conductor).size().reset_index(name="total")
        bat_c   = df[df["__metodo"] == "Batería Desconectada"].groupby(col_conductor).size().reset_index(name="bat_desc")
        rk = total_c.merge(bat_c, on=col_conductor, how="left").fillna(0)
        rk["pct_bat"] = (rk["bat_desc"] / rk["total"] * 100).round(1)
        rk = rk.sort_values("pct_bat").head(50)
        ranking = [{"conductor": r[col_conductor], "pct_bat": float(r["pct_bat"])} for _, r in rk.iterrows()]

    # Ranking por cantidad de baterías desconectadas (mayor a menor)
    ranking_bat_desc = []
    if col_conductor and col_metodo:
        bat_rows = df[df["__metodo"] == "Batería Desconectada"]
        if len(bat_rows) > 0:
            rb = bat_rows.groupby(col_conductor).size().reset_index(name="bat_desc")
            rb = rb.sort_values("bat_desc", ascending=False).head(50)
            ranking_bat_desc = [{"conductor": r[col_conductor], "bat_desc": int(r["bat_desc"])} for _, r in rb.iterrows()]

    cond_disp = sorted(df[col_conductor].dropna().unique().tolist()) if col_conductor else []

    return {
        "apagado_maquina": apagado_maquina,
        "apagado_conductor": apagado_conductor,
        "por_mes": por_mes,
        "por_hora": por_hora,
        "incidentes_20pct": incidentes_20,
        "ranking": ranking,
        "ranking_bat_desc": ranking_bat_desc,
        "conductores": cond_disp,
    }

# ── FastAPI ───────────────────────────────────────────────────────────────────

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="I_Site Dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

@app.get("/")
def index():
    # Raíz redirige a página de acceso denegado — el admin usa /isite-admin
    from fastapi.responses import HTMLResponse
    return HTMLResponse(
        '<html><body style="background:#0a0a0a;color:#555;font-family:sans-serif;'
        'display:flex;align-items:center;justify-content:center;height:100vh;margin:0">'
        '<p>Acceso no autorizado. Usa la URL que te proporcionó I_Site.</p></body></html>',
        status_code=403
    )

@app.get("/isite-admin")
def admin(creds: HTTPBasicCredentials = Depends(_security)):
    _verificar_admin(creds)
    return FileResponse(str(STATIC / "index.html"))

@app.get("/dashboard/{cliente}")
def dashboard_page(cliente: str):
    return FileResponse(str(STATIC / "index.html"))

@app.get("/health")
def health():
    return {"status": "ok", "db": _get_db() is not None}

@app.get("/api/clientes")
def get_clientes():
    result = []

    # En modo DB: consultar qué clientes tienen filas en cada tabla
    engine = _get_db()
    db_golpes = set()
    db_util   = set()
    if engine is not None:
        try:
            from sqlalchemy import text as _text
            with engine.connect() as conn:
                for row in conn.execute(_text("SELECT DISTINCT cliente FROM golpes")):
                    db_golpes.add(row[0])
                for row in conn.execute(_text("SELECT DISTINCT cliente FROM utilizacion")):
                    db_util.add(row[0])
        except Exception as e:
            print(f"  [DB] get_clientes error: {e}")

    def _existe_excel(carpeta, nombre_base):
        if not carpeta:
            return False
        return (carpeta / f"{nombre_base}.xlsx").exists() or bool(list(carpeta.glob(f"{nombre_base}_parte*.xlsx")))

    for key, meta in CLIENTES.items():
        if engine is not None:
            tiene_g = key in db_golpes
            tiene_u = key in db_util
            tiene_b = key in db_util  # bat usa la misma tabla utilizacion
        else:
            tiene_g = _existe_excel(meta["golpes"], "_CONSOLIDADO_GOLPES")
            tiene_u = _existe_excel(meta["util"],   "_CONSOLIDADO_UTILIZACION")
            tiene_b = _existe_excel(meta["bat"],    "_CONSOLIDADO_BATERIAS")
        result.append({"id": key, "label": meta["label"], "golpes": tiene_g, "util": tiene_u, "bat": tiene_b})
    return result

@app.get("/api/dashboard/{cliente}")
def get_dashboard(
    cliente: str,
    modulo: Optional[str] = Query(None),   # "golpes" | "util" | "bat" | None=todos
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    familia: Optional[str] = Query(None),
    site: Optional[str] = Query(None),
    conductor: Optional[str] = Query(None),
):
    if cliente not in CLIENTES:
        raise HTTPException(404, f"Cliente '{cliente}' no encontrado")

    meta = CLIENTES[cliente]
    cargar_g = modulo in (None, "golpes")
    cargar_u = modulo in (None, "util")
    cargar_b = modulo in (None, "bat")

    df_g = _leer_consolidado_golpes(meta["golpes"], cliente) if cargar_g else None
    df_u = _leer_consolidado_util(meta["util"],     cliente) if cargar_u else None
    df_b = _leer_consolidado_bat(meta["bat"],       cliente) if cargar_b else None

    golpes = _procesar_golpes(df_g, desde, hasta, familia, site, conductor) if df_g is not None else None
    util   = _procesar_util(df_u, desde, hasta, familia, site, conductor)   if df_u is not None else None
    bat    = _procesar_bat(df_b, desde, hasta, conductor)                   if df_b is not None else None

    return {
        "cliente": meta["label"],
        "actualizado": datetime.now().isoformat(),
        "golpes": golpes,
        "util": util,
        "bat": bat,
    }

if __name__ == "__main__":
    import uvicorn
    print(f"\n  I_Site Dashboard")
    print(f"  BASE: {BASE}")
    print(f"  URL:  http://localhost:8000\n")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
