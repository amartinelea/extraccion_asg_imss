# ==============================================================================
# Extracción de ASG (asegurados IMSS, datos abiertos) con filtros configurables
#
# Uso:
#   1. Edita el bloque PARÁMETROS de abajo (sectores, fracciones, fechas, etc.)
#   2. python extraer_asg.py                 descarga, filtra y agrega
#      python extraer_asg.py --solo-unir     solo rearma detalle y panel con lo ya bajado
#   3. python panel_ocupados.py              panel de personas ocupadas por clave
#
# Opcional: python extraer_asg.py configs/otro.py  usa los parámetros de ese archivo
# en lugar de los de aquí (lo que no venga en el archivo se toma de este bloque).
#
# Fuente:  http://datos.imss.gob.mx/sites/default/files/asg-AAAA-MM-DD.csv
#          (un archivo por mes, separador "|", Latin-1; diccionario en catalogos/)
# ==============================================================================

from datetime import date

# ##############################################################################
#                                  PARÁMETROS
# ##############################################################################

NOMBRE = "autopartes"             # nombra carpetas y archivos de salida
CARPETA_SALIDA = "data"           # relativa al repo o absoluta ("~/Desktop/ATDT/...")

FECHA_INI = date(2018, 1, 1)
FECHA_FIN = None                  # None = último mes cerrado; o p. ej. date(2025, 12, 1)

# ---- ACTIVIDAD ECONÓMICA -----------------------------------------------------
# Vector de claves, o False para apagar ese nivel.
# Claves en catalogos/actividades_imss.csv (o diccionario_IMSS.xlsx, columnas _2pos/_4_pos).
# Cada fila del ASG trae los tres niveles, así que SECTOR_2 = [38] toma todas las 38xx.
SECTOR_1 = False                  # división, 1 dígito      p. ej. [3]
SECTOR_2 = False                  # grupo, 2 dígitos        p. ej. [38]
SECTOR_4 = [3802, 3803, 3809, 3810, 3804]   # fracción, 4 dígitos

# Nivel al que se suman los paneles:
#   "auto" = el nivel más fino que tenga filtro (aquí, fracción)
#   o fijo: "SECTOR_1", "SECTOR_2", "SECTOR_4"
NIVEL_SECTOR = "auto"

# ---- OTROS FILTROS (vector o False) ------------------------------------------
ENTIDADES = False                 # p. ej. [11, 14] Guanajuato y Jalisco
MUNICIPIOS = False                # alfanumérico IMSS, p. ej. ["A01"]
DELEGACIONES = False
SUBDELEGACIONES = False
SEXO = False                      # 1 hombre, 2 mujer
TAMANO_PATRON = False             # ["S1", ..., "S7"]
RANGO_EDAD = False                # ["E1", ..., "E14"]
RANGO_SALARIAL = False            # ["W1", ...] en salarios mínimos
RANGO_UMA = False                 # ["W1", ...] en UMAs (desde feb-2017)
PLATAFORMA_DIGITAL = False        # [1] = trabajadores de plataformas digitales

# ---- ETIQUETAS (opcional): columna "grupo" que junta claves; None = no crearla --
ETIQUETAS = {
    "nivel": "SECTOR_4",
    "grupos": {
        "autopartes": [3802, 3803, 3809, 3810],
        "sistemas_electricos": [3804],
    },
}

# ---- PANEL AGREGADO (asg_{NOMBRE}_mensual.parquet) -----------------------------
# "SECTOR" = el nivel de NIVEL_SECTOR
AGREGAR_POR = ["fecha", "grupo", "SECTOR", "ENTIDADES", "SEXO"]
METRICAS_PANEL = ["asegurados", "ta", "teu", "tec", "tpu", "tpc", "masa_sal_ta", "masa_sal_tpu"]

# ---- PANEL DE OCUPADOS (panel_ocupados.py) -------------------------------------
PANEL_CLAVE = "SECTOR"            # "SECTOR", "SECTOR_2", "grupo", "ENTIDADES", ...
PANEL_POR = []                    # p. ej. ["ENTIDADES"]; [] = total nacional
PANEL_METRICA = "ta"              # ta = puestos de trabajo afiliados

# ---- DESCARGA ----------------------------------------------------------------
N_HILOS = 4                       # descargas simultáneas
TIMEOUT_SIN_DATOS = 60            # seg sin recibir nada antes de cortar
MAX_SEG_INTENTO = 180             # tope por intento (un mes normal tarda ~30 s)
REINTENTOS = 5

# ##############################################################################
#                     FIN DE PARÁMETROS (no hace falta editar abajo)
# ##############################################################################

import argparse
import calendar
import importlib.util
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import polars as pl

# La variable de entorno ASG_BASE_URL permite apuntar a otro servidor (pruebas)
BASE_URL = os.environ.get("ASG_BASE_URL", "http://datos.imss.gob.mx/sites/default/files/asg-{}.csv")

# Columnas del layout IMSS (nombres normalizados: minúsculas, "tamaño" -> "tamano")
DIMENSIONES = ["cve_delegacion", "cve_subdelegacion", "cve_entidad", "cve_municipio",
               "sector_economico_1", "sector_economico_2", "sector_economico_4",
               "tamano_patron", "sexo", "rango_edad", "rango_salarial", "rango_uma", "ptpd"]
COLS_ENTERAS = ["cve_delegacion", "cve_subdelegacion", "cve_entidad", "sector_economico_1",
                "sector_economico_2", "sector_economico_4", "sexo", "ptpd"]
METRICAS = ["asegurados", "no_trabajadores", "ta", "teu", "tec", "tpu", "tpc",
            "ta_sal", "teu_sal", "tec_sal", "tpu_sal", "tpc_sal",
            "masa_sal_ta", "masa_sal_teu", "masa_sal_tec", "masa_sal_tpu", "masa_sal_tpc"]

# Parámetro de filtro en la configuración -> columna del ASG
PARAMETROS_FILTRO = {
    "SECTOR_1": "sector_economico_1",      # división (1 posición)
    "SECTOR_2": "sector_economico_2",      # grupo (2 posiciones)
    "SECTOR_4": "sector_economico_4",      # fracción (4 posiciones)
    "ENTIDADES": "cve_entidad",
    "MUNICIPIOS": "cve_municipio",
    "DELEGACIONES": "cve_delegacion",
    "SUBDELEGACIONES": "cve_subdelegacion",
    "SEXO": "sexo",
    "TAMANO_PATRON": "tamano_patron",
    "RANGO_EDAD": "rango_edad",
    "RANGO_SALARIAL": "rango_salarial",
    "RANGO_UMA": "rango_uma",
    "PLATAFORMA_DIGITAL": "ptpd",
}
# Nombres cortos aceptados donde se pide una columna (ETIQUETAS, AGREGAR_POR, PANEL_*)
ALIAS_COLUMNA = {**{k.lower(): v for k, v in PARAMETROS_FILTRO.items()},
                 "fracciones": "sector_economico_4", "entidad": "cve_entidad",
                 "municipio": "cve_municipio"}


NIVELES_SECTOR = ["sector_economico_4", "sector_economico_2", "sector_economico_1"]  # fino -> grueso


def columna(nombre, nivel_sector=None):
    """'SECTOR_4', 'sector_4' o 'sector_economico_4' -> 'sector_economico_4'.
    'SECTOR' (sin número) -> el nivel de agregación de actividad de la extracción."""
    n = str(nombre).strip().lower()
    if n == "sector":
        if nivel_sector is None:
            sys.exit("'SECTOR' necesita una configuración cargada para saber el nivel.")
        return nivel_sector
    return ALIAS_COLUMNA.get(n, nombre)


def resolver_nivel(nivel, filtros):
    """NIVEL_SECTOR = 'auto' -> el nivel más fino que tenga filtro; si no hay, fracción."""
    if str(nivel).strip().lower() != "auto":
        col = columna(nivel)
        if col not in NIVELES_SECTOR:
            sys.exit(f"NIVEL_SECTOR debe ser 'auto', 'SECTOR_1', 'SECTOR_2' o 'SECTOR_4' (no {nivel}).")
        return col
    for col in NIVELES_SECTOR:
        if col in filtros:
            return col
    return "sector_economico_4"


NOMBRES_PARAMETROS = [
    "NOMBRE", "CARPETA_SALIDA", "FECHA_INI", "FECHA_FIN", *PARAMETROS_FILTRO, "NIVEL_SECTOR",
    "ETIQUETAS", "AGREGAR_POR", "METRICAS_PANEL", "PANEL_CLAVE", "PANEL_POR", "PANEL_METRICA",
    "N_HILOS", "TIMEOUT_SIN_DATOS", "MAX_SEG_INTENTO", "REINTENTOS"]
DEFAULTS = {k: globals()[k] for k in NOMBRES_PARAMETROS}   # los del bloque PARÁMETROS


# CONFIGURACIÓN __________________________________________________________________

RAIZ = Path(__file__).resolve().parent


def ruta_salida(cfg):
    """CARPETA_SALIDA absoluta; si es relativa, se toma desde la carpeta del repo."""
    p = Path(cfg["CARPETA_SALIDA"]).expanduser()
    return p if p.is_absolute() else RAIZ / p


def cargar_config(ruta=None):
    """Parámetros del bloque de arriba; si se da un archivo de configs/, este los reemplaza."""
    cfg = dict(DEFAULTS)
    mod = None
    if ruta:
        spec = importlib.util.spec_from_file_location("config_asg", ruta)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cfg.update({k: getattr(mod, k) for k in DEFAULTS if hasattr(mod, k)})

    if not cfg["NOMBRE"]:
        sys.exit("La configuración necesita NOMBRE (se usa para nombrar carpetas y archivos).")

    if mod is not None and hasattr(mod, "FILTROS"):
        sys.exit("FILTROS ya no se usa: pon cada filtro como variable (SECTOR_4 = [...], "
                 "ENTIDADES = False, etc.). Ver configs/plantilla.py.")
    if mod is not None and hasattr(mod, "FRACCIONES"):   # alias cómodo de SECTOR_4
        if getattr(mod, "SECTOR_4", False) is not False:
            sys.exit("Usa FRACCIONES o SECTOR_4, no ambos.")
        cfg["SECTOR_4"] = mod.FRACCIONES

    filtros = {}
    for param, col in PARAMETROS_FILTRO.items():
        valores = cfg[param]
        if valores is False or valores is None:
            continue
        if valores is True:
            sys.exit(f"{param} = True no significa nada; usa False o un vector de valores.")
        if isinstance(valores, (int, str)):
            valores = [valores]
        valores = list(valores)
        if not valores:
            sys.exit(f"{param} es un vector vacío; usa False para no filtrar.")
        filtros[col] = valores
    cfg["FILTROS"] = filtros

    # Coherencia entre niveles: cada fracción debe caer en algún grupo pedido
    s2, s4 = filtros.get("sector_economico_2"), filtros.get("sector_economico_4")
    if s2 and s4:
        fuera = [f for f in s4 if int(str(f).zfill(4)[:2]) not in {int(g) for g in s2}]
        if fuera:
            print(f"AVISO: estas fracciones no están en SECTOR_2 {s2} y quedarán fuera: {fuera}")

    # Nivel de agregación de actividad y nombres cortos -> columnas
    nivel = resolver_nivel(cfg["NIVEL_SECTOR"], filtros)
    cfg["NIVEL_SECTOR"] = nivel
    cfg["AGREGAR_POR"] = [columna(c, nivel) for c in cfg["AGREGAR_POR"]]
    cfg["PANEL_CLAVE"] = columna(cfg["PANEL_CLAVE"], nivel)
    cfg["PANEL_POR"] = [columna(c, nivel) for c in cfg["PANEL_POR"]]

    et = cfg["ETIQUETAS"]
    if et:
        et = dict(et, nivel=columna(et.get("nivel")))
        if et["nivel"] not in DIMENSIONES or not isinstance(et.get("grupos"), dict):
            sys.exit('ETIQUETAS debe ser {"nivel": "SECTOR_4", "grupos": {"nombre": [valores]}} o None.')
        cfg["ETIQUETAS"] = et
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
                esperado = r.headers.get("Content-Length")
                recibido = 0
                while True:
                    bloque = r.read1(256 * 1024)   # devuelve lo que haya llegado, sin esperar el bloque completo
                    if not bloque:
                        break
                    fh.write(bloque)
                    recibido += len(bloque)
                    if time.time() - t_ini > cfg["MAX_SEG_INTENTO"]:   # servidor a cuentagotas
                        raise TimeoutError(f"más de {cfg['MAX_SEG_INTENTO']} s descargando")
            if esperado is not None and recibido != int(esperado):
                raise IOError(f"descarga incompleta ({recibido:,} de {int(esperado):,} bytes)")
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
        if "sector_economico_4" not in lf.collect_schema().names():
            raise ValueError("el archivo no tiene el formato del ASG")
        for col, valores in cfg["FILTROS"].items():
            lf = lf.filter(condicion(col, valores))
        df = tipar(lf.collect()).with_columns(fecha=pl.lit(date.fromisoformat(f)))
        parcial = out.with_suffix(".parquet.tmp")      # escritura atómica
        df.write_parquet(parcial)
        parcial.rename(out)
    except Exception as e:                             # archivo dañado: no tumba la corrida
        return f, f"NO DISPONIBLE (archivo inválido: {str(e).splitlines()[0][:120]})"
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
    ap.add_argument("config", nargs="?", default=None,
                    help="opcional: archivo de configs/ que reemplaza los PARÁMETROS de arriba")
    ap.add_argument("--solo-unir", action="store_true",
                    help="no descarga; solo rearma detalle y panel con los meses guardados")
    args = ap.parse_args()

    cfg = cargar_config(args.config)
    carpeta_salida = ruta_salida(cfg)
    carpeta_mes = carpeta_salida / f"asg_{cfg['NOMBRE']}_meses"
    carpeta_mes.mkdir(parents=True, exist_ok=True)

    if not args.solo_unir:
        revisar_firma(carpeta_mes, cfg["FILTROS"])
        if not cfg["FILTROS"]:
            print("AVISO: sin filtros se guarda el ASG completo (millones de filas por mes).")
        fechas = fechas_corte(cfg["FECHA_INI"], cfg["FECHA_FIN"])
        print(f"[{cfg['NOMBRE']}] {len(fechas)} meses, {cfg['N_HILOS']} descargas simultáneas")
        print(f"  filtros: {cfg['FILTROS'] or 'ninguno'}")
        print(f"  nivel de agregación de actividad: {cfg['NIVEL_SECTOR']}")
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
