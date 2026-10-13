# ==============================================================================
# Extracción de ASG (asegurados IMSS, datos abiertos) con filtros configurables
#
# Uso:
#   python extraer_asg.py configs/autopartes.py            descarga, filtra y agrega
#   python extraer_asg.py configs/autopartes.py --solo-unir  solo rearma detalle y panel
#
# Toda la configuración (fechas, filtros, etiquetas, agregación, carpeta de salida)
# vive en el archivo de configs/. Ver configs/plantilla.py.
#
# Fuente:  http://datos.imss.gob.mx/sites/default/files/asg-AAAA-MM-DD.csv
#          (un archivo por mes, separador "|", Latin-1; diccionario en catalogos/)
# ==============================================================================

import argparse
import calendar
import importlib.util
import json
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import polars as pl

BASE_URL = "http://datos.imss.gob.mx/sites/default/files/asg-{}.csv"

# Columnas del layout IMSS (nombres normalizados: minúsculas, "tamaño" -> "tamano")
DIMENSIONES = ["cve_delegacion", "cve_subdelegacion", "cve_entidad", "cve_municipio",
               "sector_economico_1", "sector_economico_2", "sector_economico_4",
               "tamano_patron", "sexo", "rango_edad", "rango_salarial", "rango_uma", "ptpd"]
COLS_ENTERAS = ["cve_delegacion", "cve_subdelegacion", "cve_entidad", "sector_economico_1",
                "sector_economico_2", "sector_economico_4", "sexo", "ptpd"]
METRICAS = ["asegurados", "no_trabajadores", "ta", "teu", "tec", "tpu", "tpc",
            "ta_sal", "teu_sal", "tec_sal", "tpu_sal", "tpc_sal",
            "masa_sal_ta", "masa_sal_teu", "masa_sal_tec", "masa_sal_tpu", "masa_sal_tpc"]

DEFAULTS = dict(
    NOMBRE=None,
    FECHA_INI=date(2018, 1, 1),
    FECHA_FIN=None,                 # None = último mes cerrado
    FILTROS={},
    ETIQUETAS=None,
    AGREGAR_POR=["fecha"],
    METRICAS_PANEL=["asegurados", "ta", "tpu", "teu", "masa_sal_ta"],
    CARPETA_SALIDA="data",
    PANEL_CLAVE="sector_economico_4",   # para panel_ocupados.py
    PANEL_POR=[],
    PANEL_METRICA="ta",
    N_HILOS=4,
    TIMEOUT_SIN_DATOS=60,
    MAX_SEG_INTENTO=180,
    REINTENTOS=5,
)


# CONFIGURACIÓN __________________________________________________________________

def cargar_config(ruta):
    spec = importlib.util.spec_from_file_location("config_asg", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = dict(DEFAULTS)
    cfg.update({k: getattr(mod, k) for k in DEFAULTS if hasattr(mod, k)})

    if not cfg["NOMBRE"]:
        sys.exit("La configuración necesita NOMBRE (se usa para nombrar carpetas y archivos).")

    filtros = {}
    for col, valores in (cfg["FILTROS"] or {}).items():
        if col not in DIMENSIONES:
            sys.exit(f"FILTROS: '{col}' no es una columna del ASG. Opciones: {DIMENSIONES}")
        if valores is False or valores is None:
            continue
        if isinstance(valores, (int, str)):
            valores = [valores]
        valores = list(valores)
        if not valores:
            sys.exit(f"FILTROS: '{col}' tiene una lista vacía; usa False para no filtrar.")
        filtros[col] = valores
    cfg["FILTROS"] = filtros

    et = cfg["ETIQUETAS"]
    if et:
        if et.get("nivel") not in DIMENSIONES or not isinstance(et.get("grupos"), dict):
            sys.exit('ETIQUETAS debe ser {"nivel": <columna>, "grupos": {"nombre": [valores]}} o None.')
    return cfg


def es_entera(v):
    return isinstance(v, int) and not isinstance(v, bool)


def condicion(col, valores):
    """Expresión polars para 'col está en valores' (enteros o texto)."""
    if all(es_entera(v) for v in valores):
        return pl.col(col).cast(pl.Int64, strict=False).is_in(valores)
    return pl.col(col).cast(pl.Utf8).str.strip_chars().str.to_uppercase().is_in(
        [str(v).strip().upper() for v in valores])


def normalizar_nombre(c):
    c = c.strip().lower()
    if c.startswith("tama") and c.endswith("patron"):   # "tamaño_patron" llega con ñ rota
        return "tamano_patron"
    return c


# FECHAS _________________________________________________________________________

def fechas_corte(ini, fin):
    if fin is None:
        hoy = date.today()
        fin = date(hoy.year - (hoy.month == 1), 12 if hoy.month == 1 else hoy.month - 1, 1)
    out, (y, m) = [], (ini.year, ini.month)
    while (y, m) <= (fin.year, fin.month):
        out.append(date(y, m, calendar.monthrange(y, m)[1]).isoformat())
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


# CACHÉ DE MESES __________________________________________________________________

def revisar_firma(carpeta_mes, filtros):
    """Los meses guardados solo sirven si se filtraron igual. Guarda/compara la firma."""
    firma = {k: sorted({str(x).strip().upper() for x in v}) for k, v in sorted(filtros.items())}
    ruta = carpeta_mes / "_filtros.json"
    if ruta.exists():
        previa = json.loads(ruta.read_text(encoding="utf-8"))
        if previa != firma:
            sys.exit(
                f"Los meses en {carpeta_mes} se filtraron con otros FILTROS:\n  {previa}\n"
                f"y la configuración actual pide:\n  {firma}\n"
                "Cambia NOMBRE para hacer una extracción nueva, o borra esa carpeta.")
    else:
        if any(carpeta_mes.glob("asg_*.parquet")):
            print(f"AVISO: {carpeta_mes} ya tenía meses sin _filtros.json; "
                  "se asume que usan los FILTROS actuales.")
        ruta.write_text(json.dumps(firma, ensure_ascii=False, indent=2), encoding="utf-8")


# DESCARGA Y FILTRO DE UN MES ________________________________________________________

def descargar(url, tmp, cfg, f):
    error = None
    for intento in range(1, cfg["REINTENTOS"] + 1):
        try:
            with urllib.request.urlopen(url, timeout=cfg["TIMEOUT_SIN_DATOS"]) as r, \
                 open(tmp, "wb") as fh:
                t_ini = time.time()
                while True:
                    bloque = r.read1(256 * 1024)   # devuelve lo que haya llegado, sin esperar el bloque completo
                    if not bloque:
                        break
                    fh.write(bloque)
                    if time.time() - t_ini > cfg["MAX_SEG_INTENTO"]:   # servidor a cuentagotas
                        raise TimeoutError(f"más de {cfg['MAX_SEG_INTENTO']} s descargando")
            return None
        except urllib.error.HTTPError as e:      # 404 etc.: no tiene caso reintentar
            return e
        except Exception as e:                   # conexión colgada o cortada: reintenta
            error = e
            tmp.unlink(missing_ok=True)
            print(f"  {f}: intento {intento} falló ({e}); reintentando", flush=True)
            time.sleep(5 * intento)
    return error


def tipar(df):
    cols = df.columns
    return df.with_columns(
        [pl.col(c).cast(pl.Int32, strict=False) for c in COLS_ENTERAS if c in cols]
        + [pl.col(c).cast(pl.Float64, strict=False) for c in METRICAS if c in cols])


def procesar(f, tmpdir, cfg, carpeta_mes):
    out = carpeta_mes / f"asg_{f}.parquet"
    if out.exists():
        return f, "ya existía"
    tmp = Path(tmpdir) / f"asg-{f}.csv"
    t0 = time.time()
    error = descargar(BASE_URL.format(f), tmp, cfg, f)
    if error is not None:
        tmp.unlink(missing_ok=True)
        return f, f"NO DISPONIBLE ({error})"
    try:
        lf = pl.scan_csv(tmp, separator="|", encoding="utf8-lossy", infer_schema=False)
        lf = lf.rename({c: normalizar_nombre(c) for c in lf.collect_schema().names()})
        for col, valores in cfg["FILTROS"].items():
            lf = lf.filter(condicion(col, valores))
        df = tipar(lf.collect()).with_columns(fecha=pl.lit(date.fromisoformat(f)))
        parcial = out.with_suffix(".parquet.tmp")      # escritura atómica
        df.write_parquet(parcial)
        parcial.rename(out)
    finally:
        tmp.unlink(missing_ok=True)
    return f, f"{df.height:,} filas ({time.time() - t0:.0f} s)"


# UNIR Y AGREGAR _____________________________________________________________________

def etiquetar(det, et):
    if not et:
        return det
    expr = None
    for nombre, valores in et["grupos"].items():
        cond = condicion(et["nivel"], list(valores))
        expr = pl.when(cond).then(pl.lit(nombre)) if expr is None else expr.when(cond).then(pl.lit(nombre))
    return det.with_columns(grupo=expr.otherwise(pl.lit("otros")))


def unir_y_agregar(cfg, carpeta_mes, carpeta_salida):
    archivos = sorted(carpeta_mes.glob("asg_*.parquet"))
    if not archivos:
        sys.exit("No hay meses descargados para unir.")
    det = pl.concat([pl.read_parquet(a) for a in archivos], how="diagonal_relaxed")
    det = etiquetar(det, cfg["ETIQUETAS"])
    nombre = cfg["NOMBRE"]
    det.write_parquet(carpeta_salida / f"asg_{nombre}_detalle.parquet")

    por = [c for c in cfg["AGREGAR_POR"] if c in det.columns]
    faltan = set(cfg["AGREGAR_POR"]) - set(por)
    if faltan:
        print(f"AVISO: AGREGAR_POR ignora columnas que no existen: {sorted(faltan)}")
    metricas = [c for c in cfg["METRICAS_PANEL"] if c in det.columns]
    pan = det.group_by(por).agg([pl.col(c).sum() for c in metricas])
    if {"masa_sal_ta", "ta"} <= set(metricas):
        pan = pan.with_columns(
            salario_diario_prom=pl.when(pl.col("ta") > 0).then(pl.col("masa_sal_ta") / pl.col("ta")))
    pan = pan.sort(por)
    pan.write_parquet(carpeta_salida / f"asg_{nombre}_mensual.parquet")

    meses = det["fecha"].n_unique()
    print(f"Listo: {meses} meses, {det.height:,} filas de detalle, {pan.height:,} filas de panel.")
    print(f"  {carpeta_salida / f'asg_{nombre}_detalle.parquet'}")
    print(f"  {carpeta_salida / f'asg_{nombre}_mensual.parquet'}")


# MAIN _______________________________________________________________________________

def main():
    ap = argparse.ArgumentParser(description="Extrae ASG del IMSS con filtros configurables.")
    ap.add_argument("config", help="archivo de configuración, p. ej. configs/autopartes.py")
    ap.add_argument("--solo-unir", action="store_true",
                    help="no descarga; solo rearma detalle y panel con los meses guardados")
    args = ap.parse_args()

    cfg = cargar_config(args.config)
    carpeta_salida = Path(cfg["CARPETA_SALIDA"]).expanduser()
    carpeta_mes = carpeta_salida / f"asg_{cfg['NOMBRE']}_meses"
    carpeta_mes.mkdir(parents=True, exist_ok=True)

    if not args.solo_unir:
        revisar_firma(carpeta_mes, cfg["FILTROS"])
        if not cfg["FILTROS"]:
            print("AVISO: sin filtros se guarda el ASG completo (millones de filas por mes).")
        fechas = fechas_corte(cfg["FECHA_INI"], cfg["FECHA_FIN"])
        print(f"[{cfg['NOMBRE']}] {len(fechas)} meses, {cfg['N_HILOS']} descargas simultáneas")
        print(f"  filtros: {cfg['FILTROS'] or 'ninguno'}")
        no_disp = []
        with tempfile.TemporaryDirectory(prefix="asg_crudos_") as tmpdir, \
             ThreadPoolExecutor(max_workers=cfg["N_HILOS"]) as ex:
            futuros = [ex.submit(procesar, f, tmpdir, cfg, carpeta_mes) for f in fechas]
            for fut in as_completed(futuros):
                f, msg = fut.result()
                if msg != "ya existía":
                    print(f"  {f}: {msg}", flush=True)
                if msg.startswith("NO DISPONIBLE"):
                    no_disp.append(f)
        if no_disp:
            print(f"Meses no disponibles ({len(no_disp)}): {sorted(no_disp)}. "
                  "Vuelve a correr para reintentarlos.")

    unir_y_agregar(cfg, carpeta_mes, carpeta_salida)


if __name__ == "__main__":
    main()
