"""
upload_db.py
═══════════════════════════════════════════════════════════
Sube todos los consolidados (golpes + utilización) a PostgreSQL.
Corre después de consolidar_todos.py o después de descargar nuevos archivos.

Uso:
  python upload_db.py                    ← sube todos los clientes
  python upload_db.py --cliente watts    ← solo un cliente
  python upload_db.py --dry-run          ← muestra qué haría, sin subir
═══════════════════════════════════════════════════════════
"""
import os, sys, argparse
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text

# ── Config ────────────────────────────────────────────────────────────────────

def _base():
    onedrive = Path(os.path.expanduser("~")) / "OneDrive - Arrendamiento de Maquinaria SPA" / "I_SITE - Documentos"
    legacy   = Path(r"C:\Users\Notebook\Arrendamiento de Maquinaria SPA\I_SITE - Documentos")
    return onedrive if onedrive.exists() else legacy

BASE = _base()

CLIENTES = {
    "watts":        {"golpes": BASE/"WATT'S/Dashboard - Watts/Golpes Watts",          "util": BASE/"WATT'S/Dashboard - Watts/Utilización Watts"},
    "adidas":       {"golpes": BASE/"Adidas/Golpes Adidas",                            "util": BASE/"Adidas/Utilización Adidas"},
    "agrocommerce": {"golpes": BASE/"Agrocommerce/Golpes Agrocommerce",                "util": BASE/"Agrocommerce/Utilización Agrocommerce"},
    "agrosuper":    {"golpes": BASE/"AGROSUPER/Dashboard - Agrosuper/Golpes Agrosuper","util": BASE/"AGROSUPER/Dashboard - Agrosuper/Utilización Agrosuper"},
    "arcor":        {"golpes": BASE/"Arcor/Golpes Arcor",                              "util": BASE/"Arcor/Utilización Arcor"},
    "ariztia":      {"golpes": BASE/"Ariztia/Golpes Ariztia",                          "util": BASE/"Ariztia/Utilización Ariztia"},
    "ascend":       {"golpes": BASE/"Ascend Laboratories SpA/Golpes Ascend",           "util": BASE/"Ascend Laboratories SpA/Utilización Ascend"},
    "bomi":         {"golpes": BASE/"Bomi Group/Golpes Bomi",                          "util": BASE/"Bomi Group/Utilización Bomi"},
    "caribean":     {"golpes": BASE/"Caribean Pharma/Golpes Caribean Pharma",          "util": BASE/"Caribean Pharma/Utilización Caribean Pharma"},
    "ccu":          {"golpes": BASE/"CCU/Golpes CCU",                                  "util": BASE/"CCU/Utilización CCU"},
    "cencosud":     {"golpes": BASE/"CENCOSUD/Dashboard - Cencosud/Golpes Cencosud",   "util": BASE/"CENCOSUD/Dashboard - Cencosud/Utilización Cencosud"},
    "chilecargo":   {"golpes": BASE/"ChileCargo/Golpes ChileCargo",                    "util": BASE/"ChileCargo/Utilización ChileCargo"},
    "cial":         {"golpes": BASE/"Cial Alimentos/Golpes Cial Alimentos",            "util": BASE/"Cial Alimentos/Utilización Cial Alimentos"},
    "cmf":          {"golpes": BASE/"CMF/Golpes CMF",                                  "util": BASE/"CMF/Utilización CMF"},
    "colun":        {"golpes": BASE/"Colun/Golpes Colun",                              "util": BASE/"Colun/Utilización Colun"},
    "comaco":       {"golpes": BASE/"COMACO/Golpes COMACO",                            "util": BASE/"COMACO/Utilización COMACO"},
    "cristalerias": {"golpes": BASE/"Cristalerías Toro/Golpes Cristalerias Toro",      "util": BASE/"Cristalerías Toro/Utilización Cristalerias Toro"},
    "din":          {"golpes": BASE/"DIN S.A./Golpes DIN",                             "util": BASE/"DIN S.A./Utilización DIN"},
    "dragpharma":   {"golpes": BASE/"Laboratorio Dragpharma/Golpes Dragpharma",        "util": BASE/"Laboratorio Dragpharma/Utilización Dragpharma"},
    "egakat":       {"golpes": BASE/"EGAKAT/Golpes Egakat",                            "util": BASE/"EGAKAT/Utilización Egakat"},
    "embonor":      {"golpes": BASE/"Coca Cola Embonor/Golpes Embonor",                "util": BASE/"Coca Cola Embonor/Utilización Embonor"},
    "fedex":        {"golpes": BASE/"Fedex/Golpes Fedex",                              "util": BASE/"Fedex/Utilización Fedex"},
    "friofort":     {"golpes": BASE/"FRIOFORT/Golpes Friofort",                        "util": BASE/"FRIOFORT/Utilización Friofort"},
    "hoffens":      {"golpes": BASE/"Hoffens/Golpes Hoffens",                          "util": BASE/"Hoffens/Utilización Hoffens"},
    "icb":          {"golpes": BASE/"ICB S.A./Golpes ICB",                             "util": BASE/"ICB S.A./Utilización ICB"},
    "imicar":       {"golpes": BASE/"IMICAR/Golpes IMICAR",                            "util": BASE/"IMICAR/Utilización IMICAR"},
    "imega":        {"golpes": BASE/"Imega Ventus/Golpes Imega Ventus",                "util": BASE/"Imega Ventus/Utilización Imega Ventus"},
    "imperial":     {"golpes": BASE/"Imperial/Golpes Imperial",                        "util": BASE/"Imperial/Utilización Imperial"},
    "intcomex":     {"golpes": BASE/"Intcomex/Golpes Intcomex",                        "util": BASE/"Intcomex/Utilización Intcomex"},
    "int-paper":    {"golpes": BASE/"Internacional Paper/Golpes Internacional Paper",  "util": BASE/"Internacional Paper/Utilización Internacional Paper"},
    "keylogistics": {"golpes": BASE/"Keylogistics/Golpes Keylogistics",                "util": BASE/"Keylogistics/Utilización Keylogistics"},
    "kuehne":       {"golpes": BASE/"Kuehne + Nagel/Golpes Kuehne Nagel",              "util": BASE/"Kuehne + Nagel/Utilización Kuehne Nagel"},
    "lapolar":      {"golpes": BASE/"Empresas La Polar/Golpes La Polar",               "util": BASE/"Empresas La Polar/Utilización La Polar"},
    "logisfashion": {"golpes": BASE/"Logisfashion/Golpes Logisfashion",                "util": BASE/"Logisfashion/Utilización Logisfashion"},
    "loreal":       {"golpes": BASE/"L'OREAL/Golpes LOREAL",                           "util": BASE/"L'OREAL/Utilización LOREAL"},
    "nestle":       {"golpes": BASE/"Nestlé/Golpes Nestle",                            "util": BASE/"Nestlé/Utilización Nestle"},
    "prisa":        {"golpes": BASE/"PRISA/Golpes PRISA",                              "util": BASE/"PRISA/Utilización PRISA"},
    "puma":         {"golpes": BASE/"PUMA/Golpes PUMA",                                "util": BASE/"PUMA/Utilización PUMA"},
    "quelen":       {"golpes": BASE/"Quelen Export/Golpes Quelen Export",              "util": BASE/"Quelen Export/Utilización Quelen Export"},
    "recilar":      {"golpes": BASE/"Re-cilar/Golpes Re-ciclar",                       "util": BASE/"Re-cilar/Utilización Re-ciclar"},
    "rosen":        {"golpes": BASE/"ROSEN/Golpes ROSEN",                              "util": BASE/"ROSEN/Utilización ROSEN"},
    "sherwin":      {"golpes": BASE/"Sherwin Williams/Golpes Sherwin Williams",        "util": BASE/"Sherwin Williams/Utilización Sherwin Williams"},
    "smu":          {"golpes": BASE/"SMU/Golpes SMU",                                  "util": BASE/"SMU/Utilización SMU"},
    "tecnored":     {"golpes": BASE/"TecnoRed/Golpes TecnoRed",                        "util": BASE/"TecnoRed/Utilización TecnoRed"},
    "tottus":       {"golpes": BASE/"Tottus/Golpes Tottus",                            "util": BASE/"Tottus/Utilización Tottus"},
    "unilever":     {"golpes": BASE/"Unilever/Golpes Unilever",                        "util": BASE/"Unilever/Utilización Unilever"},
    "colun":        {"golpes": BASE/"Colun/Golpes Colun",                              "util": BASE/"Colun/Utilización Colun"},
}

# ── Mapeo de columnas Excel → DB ──────────────────────────────────────────────
# Se busca por substring case-insensitive en el nombre de columna del Excel

GOLPES_MAP = [
    (["máquina", "maquina"],                     "maquina"),
    (["flota"],                                   "nro_flota"),
    (["familia"],                                 "familia"),
    (["modelo"],                                  "modelo"),
    (["marca"],                                   "marca"),
    (["site"],                                    "site"),
    (["conductor"],                               "conductor"),
    (["nivel"],                                   "nivel"),
    (["hora", "fecha"],                           "hora_golpe"),
    (["descarga", "batería", "bateria"],          "descarga_bateria"),
    (["velocidad"],                               "velocidad"),
    (["traccionando"],                            "traccionando"),
    (["elevando"],                                "elevando"),
]

UTIL_MAP = [
    (["máquina", "maquina"],                     "maquina"),
    (["flota"],                                   "nro_flota"),
    (["familia"],                                 "familia"),
    (["modelo"],                                  "modelo"),
    (["marca"],                                   "marca"),
    (["site"],                                    "site"),
    (["conductor"],                               "conductor"),
    (["inicio"],                                  "inicio"),
    (["llave"],                                   "seg_llave"),
    (["funcionam"],                               "seg_funcionam"),
    (["tracci"],                                  "seg_traccion"),
    (["elevaci"],                                 "seg_elevacion"),
    (["ratio"],                                   "ratio_func_llave"),
    (["método", "metodo"],                        "metodo_apagado"),
    (["clave"],                                   "claves_compartidas"),
]

def _find_col(df_cols, keywords):
    """Devuelve la primera columna que contiene alguna keyword (case-insensitive)."""
    for kw in keywords:
        for col in df_cols:
            if kw.lower() in col.lower():
                return col
    return None

def _mapear(df, col_map):
    """Renombra columnas del Excel según el mapa, descarta las que no se reconocen."""
    rename = {}
    for keywords, db_col in col_map:
        src = _find_col(df.columns, keywords)
        if src and src not in rename:
            rename[src] = db_col
    df = df.rename(columns=rename)
    cols_validas = [db_col for _, db_col in col_map if db_col in df.columns]
    return df[cols_validas].copy()

# ── Lector de archivos ────────────────────────────────────────────────────────

def _leer_archivos(carpeta: Path, tipo: str) -> pd.DataFrame | None:
    """
    Lee consolidado o archivos mensuales de una carpeta.
    tipo: "golpes" | "util"
    """
    if not carpeta or not carpeta.exists():
        return None

    nombre_base = "_CONSOLIDADO_GOLPES" if tipo == "golpes" else "_CONSOLIDADO_UTILIZACION"

    # 1. Archivo consolidado único
    f = carpeta / f"{nombre_base}.xlsx"
    if f.exists():
        return pd.read_excel(f, engine="openpyxl")

    # 2. Partes consolidadas (_parte1, _parte2, ...)
    partes = sorted(p for p in carpeta.glob(f"{nombre_base}_parte*.xlsx")
                    if p.stem.split("_parte")[-1].isdigit())
    if partes:
        return pd.concat([pd.read_excel(p, engine="openpyxl") for p in partes], ignore_index=True)

    # 3. Archivos mensuales raw (Golpes_CLIENTE_Mes.xlsx / Actividad_CLIENTE_Mes.xlsx)
    prefijo = "Golpes_" if tipo == "golpes" else "Actividad_"
    raws = sorted(carpeta.glob(f"{prefijo}*.xlsx"))
    if raws:
        frames = []
        for r in raws:
            try:
                df = pd.read_excel(r, header=4, engine="openpyxl")
                # Descartar filas completamente vacías
                df = df.dropna(how="all")
                if len(df) > 0:
                    frames.append(df)
            except Exception as e:
                print(f"  ⚠ No se pudo leer {r.name}: {e}")
        if frames:
            return pd.concat(frames, ignore_index=True)

    return None

# ── Upload principal ──────────────────────────────────────────────────────────

def subir_cliente(cliente: str, rutas: dict, engine, dry_run: bool = False):
    print(f"\n── {cliente.upper()} ──")

    for tipo, tabla, col_map in [
        ("golpes", "golpes",     GOLPES_MAP),
        ("util",   "utilizacion", UTIL_MAP),
    ]:
        carpeta = rutas.get(tipo)
        df_raw = _leer_archivos(carpeta, tipo)

        if df_raw is None or len(df_raw) == 0:
            print(f"  {tipo}: sin datos")
            continue

        df = _mapear(df_raw, col_map)
        df["cliente"] = cliente
        df = df.dropna(how="all")

        print(f"  {tipo}: {len(df):,} filas", end="")

        if dry_run:
            print(" [dry-run, no se sube]")
            continue

        # Borrar registros anteriores del cliente en esta tabla y reinsertar
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {tabla} WHERE cliente = :c"), {"c": cliente})

        df.to_sql(tabla, engine, if_exists="append", index=False, method="multi", chunksize=5000)
        print(" ✓ subido")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cliente", default=None, help="Sube solo este cliente")
    parser.add_argument("--dry-run", action="store_true", help="Sin escribir en DB")
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        print("ERROR: Variable de entorno DATABASE_URL no definida.")
        print("  Ejemplo: set DATABASE_URL=postgresql://user:pass@host:5432/dbname")
        sys.exit(1)

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url, pool_pre_ping=True)
    print(f"Conectado a DB.")
    print(f"BASE: {BASE}")

    clientes = {args.cliente: CLIENTES[args.cliente]} if args.cliente else CLIENTES

    ok = err = 0
    for key, rutas in clientes.items():
        try:
            subir_cliente(key, rutas, engine, dry_run=args.dry_run)
            ok += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            err += 1

    print(f"\n{'='*50}")
    print(f"  Clientes OK   : {ok}")
    print(f"  Clientes error: {err}")


if __name__ == "__main__":
    main()
