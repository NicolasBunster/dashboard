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

import pandas as pd
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

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

CLIENTE_ID    = "cencosud"
CLIENTE_LABEL = "CENCOSUD"
CLIENTE_META  = {
    "golpes": BASE / "CENCOSUD/Dashboard - Cencosud/Golpes Cencosud",
    "util":   BASE / "CENCOSUD/Dashboard - Cencosud/Utilización Cencosud",
    "bat":    BASE / "CENCOSUD/Dashboard - Cencosud/Baterías Cencosud",
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

    col_velocidad = next((c for c in df.columns if "velocidad" in c.lower()), None)

    total = len(df)
    if total == 0:
        return {"kpis": {}, "por_familia": [], "por_mes": [], "ultimos_30dias": [], "ranking": [],
                "por_maquina": [], "por_site": [], "por_hora": [], "por_dia_semana": [],
                "sites": [], "familias": [], "conductores": []}

    df_altos = df[df[col_nivel].str.lower().str.contains("altos", na=False)] if col_nivel else df.iloc[0:0]
    df_medios = df[df[col_nivel].str.lower().str.contains("medios", na=False)] if col_nivel else df.iloc[0:0]

    # KPIs
    altos  = len(df_altos)
    medios = len(df_medios)
    bajos  = total - altos - medios
    n_conductores = int(df[col_conductor].nunique()) if col_conductor else 0
    n_maquinas    = int(df[col_maquina].nunique()) if col_maquina else 0
    bat_desc      = int(df[col_bat].sum()) if col_bat else 0
    pct_altos     = round(altos / total * 100, 1) if total else 0
    vel_prom      = round(float(df_altos[col_velocidad].mean()), 1) if col_velocidad and len(df_altos) else 0

    # Por familia (donut golpes altos)
    por_familia = []
    if col_familia:
        gf = df_altos.groupby(col_familia).size().reset_index(name="total")
        por_familia = [{"familia": r[col_familia], "total": int(r["total"])} for _, r in gf.iterrows()]

    # Por mes — altos Y medios en la misma serie
    por_mes = []
    if col_fecha:
        dm = df.copy()
        dm["mes"] = dm["__fecha"].dt.to_period("M").astype(str)
        ga = dm[dm[col_nivel].str.lower().str.contains("altos",  na=False)].groupby("mes").size().rename("altos")  if col_nivel else pd.Series(dtype=int)
        gm = dm[dm[col_nivel].str.lower().str.contains("medios", na=False)].groupby("mes").size().rename("medios") if col_nivel else pd.Series(dtype=int)
        merged = pd.concat([ga, gm], axis=1).fillna(0).sort_index()
        por_mes = [{"mes": idx, "altos": int(r.get("altos", 0)), "medios": int(r.get("medios", 0))}
                   for idx, r in merged.iterrows()]

    # Últimos 30 días — altos Y medios
    ultimos_30 = []
    if col_fecha:
        hoy = datetime.now()
        d30 = df[df["__fecha"] >= hoy - timedelta(days=30)].copy()
        d30["fecha_str"] = d30["__fecha"].dt.strftime("%d/%m")
        ga2 = d30[d30[col_nivel].str.lower().str.contains("altos",  na=False)].groupby("fecha_str").size().rename("altos")  if col_nivel else pd.Series(dtype=int)
        gm2 = d30[d30[col_nivel].str.lower().str.contains("medios", na=False)].groupby("fecha_str").size().rename("medios") if col_nivel else pd.Series(dtype=int)
        merged2 = pd.concat([ga2, gm2], axis=1).fillna(0)
        # Ordenar cronológicamente por fecha real
        d30_dates = d30[["fecha_str", "__fecha"]].drop_duplicates().sort_values("__fecha")
        order = d30_dates["fecha_str"].unique().tolist()
        merged2 = merged2.reindex([f for f in order if f in merged2.index])
        ultimos_30 = [{"dia": idx, "altos": int(r.get("altos", 0)), "medios": int(r.get("medios", 0))}
                      for idx, r in merged2.iterrows()]

    # Top máquinas con más golpes altos
    por_maquina = []
    if col_maquina:
        gq = df_altos.groupby(col_maquina).size().reset_index(name="total").sort_values("total", ascending=False).head(15)
        por_maquina = [{"maquina": str(r[col_maquina]), "total": int(r["total"])} for _, r in gq.iterrows()]

    # Golpes altos por site
    por_site = []
    if col_site:
        gs = df_altos.groupby(col_site).size().reset_index(name="total").sort_values("total", ascending=False).head(15)
        por_site = [{"site": str(r[col_site]), "total": int(r["total"])} for _, r in gs.iterrows()]

    # Golpes altos por hora del día
    por_hora = []
    if col_fecha:
        df_altos2 = df_altos.copy() if "__fecha" in df_altos.columns else df_altos
        if "__fecha" in df.columns:
            df_altos2 = df[df[col_nivel].str.lower().str.contains("altos", na=False)].copy() if col_nivel else df.copy()
            df_altos2["hora"] = df_altos2["__fecha"].dt.hour
            gh = df_altos2.groupby("hora").size().reset_index(name="total").sort_values("hora")
            por_hora = [{"hora": int(r["hora"]), "total": int(r["total"])} for _, r in gh.iterrows()]

    # Golpes altos por día de la semana
    DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    por_dia_semana = []
    if col_fecha and "__fecha" in df.columns:
        da = df[df[col_nivel].str.lower().str.contains("altos", na=False)].copy() if col_nivel else df.copy()
        da["dow"] = da["__fecha"].dt.dayofweek
        gw = da.groupby("dow").size().reindex(range(7), fill_value=0)
        por_dia_semana = [{"dia": DIAS[i], "total": int(v)} for i, v in gw.items()]

    # Ranking conductores por golpes altos
    ranking = []
    if col_conductor:
        ra = df_altos.groupby(col_conductor).size().reset_index(name="golpes_altos")
        ra = ra.sort_values("golpes_altos", ascending=False).head(50)
        ranking = [{"conductor": r[col_conductor], "golpes_altos": int(r["golpes_altos"])} for _, r in ra.iterrows()]

    sites_disp = sorted(df[col_site].dropna().unique().tolist()) if col_site else []
    fam_disp   = sorted(df[col_familia].dropna().unique().tolist()) if col_familia else []
    cond_disp  = sorted(df[col_conductor].dropna().unique().tolist()) if col_conductor else []

    return {
        "kpis": {
            "total_conductores": n_conductores,
            "total_golpes": total,
            "total_golpes_altos": altos,
            "total_golpes_medios": medios,
            "total_golpes_bajos": bajos,
            "pct_altos": pct_altos,
            "total_maquinas": n_maquinas,
            "apagado_bat_desc": bat_desc,
            "velocidad_promedio": vel_prom,
        },
        "por_familia": por_familia,
        "por_mes": por_mes,
        "ultimos_30dias": ultimos_30,
        "ranking": ranking,
        "por_maquina": por_maquina,
        "por_site": por_site,
        "por_hora": por_hora,
        "por_dia_semana": por_dia_semana,
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

    col_seg_trac = next((c for c in df.columns if "tracci" in c.lower()), None)
    col_seg_elev = next((c for c in df.columns if "elevaci" in c.lower()), None)
    col_maquina  = next((c for c in df.columns if "máquina" in c.lower() or "maquina" in c.lower()), None)

    if len(df) == 0:
        return {"kpis": {}, "hrs_familia": [], "claves_conductor": [], "hrs_mes": [], "hrs_dia": [],
                "hrs_dia_semana": [], "metodo_apagado": [], "por_maquina": [],
                "ranking": [], "ranking_hrs": [], "sites": [], "familias": [], "conductores": []}

    hrs_func  = float(df[col_seg_func].sum() / 3600)  if col_seg_func  else 0
    hrs_llave = float(df[col_seg_llave].sum() / 3600) if col_seg_llave else 0
    hrs_trac  = float(df[col_seg_trac].sum() / 3600)  if col_seg_trac  else 0
    hrs_elev  = float(df[col_seg_elev].sum() / 3600)  if col_seg_elev  else 0
    n_sesiones   = len(df)
    eficiencia   = round(hrs_func / hrs_llave * 100, 1) if hrs_llave else 0
    avg_min_ses  = round(float(df[col_seg_func].mean() / 60), 1) if col_seg_func else 0
    apagado_bat  = int((df[col_metodo].str.lower().str.contains("batería|bateria", na=False)).sum()) if col_metodo else 0
    pct_bat_apag = round(apagado_bat / n_sesiones * 100, 1) if n_sesiones else 0

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
        dd["fecha_str"] = dd["__fecha"].dt.strftime("%d/%m")
        gd = dd.groupby("fecha_str")[col_seg_func].sum() / 3600
        dd_dates = dd[["fecha_str","__fecha"]].drop_duplicates().sort_values("__fecha")
        order = dd_dates["fecha_str"].unique().tolist()
        hrs_dia = [{"dia": k, "horas": round(float(gd.get(k, 0)), 1)} for k in order]

    # Hrs func por día de la semana
    DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    hrs_dia_semana = []
    if col_inicio and col_seg_func and "__fecha" in df.columns:
        dw = df.copy()
        dw["dow"] = dw["__fecha"].dt.dayofweek
        gw = dw.groupby("dow")[col_seg_func].sum() / 3600
        gw = gw.reindex(range(7), fill_value=0)
        hrs_dia_semana = [{"dia": DIAS[i], "horas": round(float(v), 1)} for i, v in gw.items()]

    # Distribución método de apagado
    metodo_apagado = []
    if col_metodo:
        gmet = df[col_metodo].value_counts()
        metodo_apagado = [{"metodo": k, "total": int(v)} for k, v in gmet.items()]

    # Top máquinas por horas func
    por_maquina = []
    if col_maquina and col_seg_func:
        gq = df.groupby(col_maquina)[col_seg_func].sum().reset_index()
        gq = gq.rename(columns={col_seg_func: "seg"})
        gq["horas"] = (gq["seg"] / 3600).round(1)
        gq = gq.sort_values("horas", ascending=False).head(15)
        por_maquina = [{"maquina": str(r[col_maquina]), "horas": float(r["horas"])} for _, r in gq.iterrows()]

    # Ranking por eficiencia
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

    # Ranking horas utilización (menor a mayor)
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
            "hrs_traccion": round(hrs_trac, 0),
            "hrs_elevacion": round(hrs_elev, 0),
            "pct_eficiencia": eficiencia,
            "n_sesiones": n_sesiones,
            "avg_min_sesion": avg_min_ses,
            "apagado_bat_desc": apagado_bat,
            "pct_bat_apagado": pct_bat_apag,
        },
        "hrs_familia": hrs_familia,
        "claves_conductor": claves_conductor,
        "hrs_mes": hrs_mes,
        "hrs_dia": hrs_dia,
        "hrs_dia_semana": hrs_dia_semana,
        "metodo_apagado": metodo_apagado,
        "por_maquina": por_maquina,
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
        return {"kpis": {}, "apagado_maquina": [], "apagado_conductor": [], "por_mes": [],
                "bat_desc_mes": [], "por_hora": [], "por_dia_semana": [],
                "incidentes_20pct": [], "ranking": [], "ranking_bat_desc": [], "conductores": []}

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

    total_ses   = len(df)
    n_bat_desc  = int((df["__metodo"] == "Batería Desconectada").sum()) if col_metodo else 0
    n_normal    = int((df["__metodo"] == "Normal").sum())               if col_metodo else 0
    n_inactiv   = int((df["__metodo"] == "Inactividad").sum())          if col_metodo else 0
    pct_bat     = round(n_bat_desc / total_ses * 100, 1) if total_ses else 0

    # Apagado por máquina (top 20 por bat_desc)
    apagado_maquina = []
    if col_maquina and col_metodo:
        gm = df.groupby([col_maquina, "__metodo"]).size().unstack(fill_value=0).reset_index()
        gm["bat_desc"] = gm.get("Batería Desconectada", 0)
        gm = gm.sort_values("bat_desc", ascending=False)
        for _, r in gm.head(20).iterrows():
            apagado_maquina.append({
                "maquina": str(r[col_maquina]),
                "normal": int(r.get("Normal", 0)),
                "bat_desc": int(r.get("Batería Desconectada", 0)),
                "inactividad": int(r.get("Inactividad", 0)),
            })

    # Apagado por conductor (top 20 por bat_desc)
    apagado_conductor = []
    if col_conductor and col_metodo:
        gc = df.groupby([col_conductor, "__metodo"]).size().unstack(fill_value=0).reset_index()
        gc["bat_desc"] = gc.get("Batería Desconectada", 0)
        gc = gc.sort_values("bat_desc", ascending=False)
        for _, r in gc.head(20).iterrows():
            apagado_conductor.append({
                "conductor": str(r[col_conductor]),
                "normal": int(r.get("Normal", 0)),
                "bat_desc": int(r.get("Batería Desconectada", 0)),
                "inactividad": int(r.get("Inactividad", 0)),
            })

    # Por mes — total sesiones
    por_mes = []
    if col_inicio and "__fecha" in df.columns:
        df["mes"] = df["__fecha"].dt.to_period("M").astype(str)
        gm2 = df.groupby("mes").size().reset_index(name="total").sort_values("mes")
        por_mes = [{"mes": r["mes"], "total": int(r["total"])} for _, r in gm2.iterrows()]

    # Bat desconectadas por mes
    bat_desc_mes = []
    if col_inicio and col_metodo and "__fecha" in df.columns:
        db = df[df["__metodo"] == "Batería Desconectada"].copy()
        db["mes"] = db["__fecha"].dt.to_period("M").astype(str)
        gbd = db.groupby("mes").size().reset_index(name="total").sort_values("mes")
        bat_desc_mes = [{"mes": r["mes"], "total": int(r["total"])} for _, r in gbd.iterrows()]

    # Por hora del día (bat desc, últimos 6 meses)
    por_hora = []
    if col_inicio and col_metodo and "__fecha" in df.columns:
        d6m = df[(df["__fecha"] >= datetime.now() - timedelta(days=180)) &
                 (df["__metodo"] == "Batería Desconectada")].copy()
        d6m["hora"] = d6m["__fecha"].dt.hour
        gh = d6m.groupby("hora").size().reindex(range(24), fill_value=0)
        por_hora = [{"hora": h, "total": int(v)} for h, v in gh.items()]

    # Por día de la semana (bat desc)
    DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    por_dia_semana = []
    if col_inicio and col_metodo and "__fecha" in df.columns:
        dw = df[df["__metodo"] == "Batería Desconectada"].copy()
        dw["dow"] = dw["__fecha"].dt.dayofweek
        gw = dw.groupby("dow").size().reindex(range(7), fill_value=0)
        por_dia_semana = [{"dia": DIAS[i], "total": int(v)} for i, v in gw.items()]

    # Incidentes batería <20%
    incidentes_20 = []
    if col_pct_fin and col_inicio and "__fecha" in df.columns:
        d_bajo = df[pd.to_numeric(df[col_pct_fin], errors="coerce") < 20].copy()
        d_bajo["mes"] = d_bajo["__fecha"].dt.to_period("M").astype(str)
        gi = d_bajo.groupby("mes").size().reset_index(name="total").sort_values("mes")
        incidentes_20 = [{"mes": r["mes"], "total": int(r["total"])} for _, r in gi.iterrows()]

    # Ranking por % bat desconectada
    ranking = []
    if col_conductor and col_metodo:
        total_c = df.groupby(col_conductor).size().reset_index(name="total")
        bat_c   = df[df["__metodo"] == "Batería Desconectada"].groupby(col_conductor).size().reset_index(name="bat_desc")
        rk = total_c.merge(bat_c, on=col_conductor, how="left").fillna(0)
        rk["pct_bat"] = (rk["bat_desc"] / rk["total"] * 100).round(1)
        rk = rk.sort_values("pct_bat", ascending=False).head(50)
        ranking = [{"conductor": r[col_conductor], "pct_bat": float(r["pct_bat"]),
                    "bat_desc": int(r["bat_desc"])} for _, r in rk.iterrows()]

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
        "kpis": {
            "total_sesiones": total_ses,
            "bat_desconectadas": n_bat_desc,
            "normal": n_normal,
            "inactividad": n_inactiv,
            "pct_bat_desc": pct_bat,
        },
        "apagado_maquina": apagado_maquina,
        "apagado_conductor": apagado_conductor,
        "por_mes": por_mes,
        "bat_desc_mes": bat_desc_mes,
        "por_hora": por_hora,
        "por_dia_semana": por_dia_semana,
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
    return FileResponse(str(STATIC / "index.html"))

@app.get("/health")
def health():
    return {"status": "ok", "db": _get_db() is not None}

@app.get("/api/dashboard")
def get_dashboard(
    modulo: Optional[str] = Query(None),   # "golpes" | "util" | "bat" | None=todos
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    familia: Optional[str] = Query(None),
    site: Optional[str] = Query(None),
    conductor: Optional[str] = Query(None),
):
    meta = CLIENTE_META
    cargar_g = modulo in (None, "golpes")
    cargar_u = modulo in (None, "util")
    cargar_b = modulo in (None, "bat")

    df_g = _leer_consolidado_golpes(meta["golpes"], CLIENTE_ID) if cargar_g else None
    df_u = _leer_consolidado_util(meta["util"],     CLIENTE_ID) if cargar_u else None
    df_b = _leer_consolidado_bat(meta["bat"],       CLIENTE_ID) if cargar_b else None

    golpes = _procesar_golpes(df_g, desde, hasta, familia, site, conductor) if df_g is not None else None
    util   = _procesar_util(df_u, desde, hasta, familia, site, conductor)   if df_u is not None else None
    bat    = _procesar_bat(df_b, desde, hasta, conductor)                   if df_b is not None else None

    return {
        "cliente": CLIENTE_LABEL,
        "actualizado": datetime.now().isoformat(),
        "golpes": golpes,
        "util": util,
        "bat": bat,
    }

if __name__ == "__main__":
    import uvicorn
    print(f"\n  I_Site Dashboard — CENCOSUD")
    print(f"  BASE: {BASE}")
    print(f"  URL:  http://localhost:8000\n")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
