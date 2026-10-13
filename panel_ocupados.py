# ==============================================================================
# Panel de personas ocupadas por clave, a partir de una extracción de ASG
#
# Uso (después de correr extraer_asg.py con la misma configuración):
#   python panel_ocupados.py configs/autopartes.py
#   python panel_ocupados.py configs/autopartes.py --clave sector_economico_2 --por cve_entidad
#   python panel_ocupados.py configs/autopartes.py --metrica asegurados
#
# "Ocupados" = puestos de trabajo afiliados (ta) por default, la cifra de empleo
# formal que reporta el IMSS. Con --metrica se puede usar asegurados, tpu, teu, etc.
#
# Salidas en CARPETA_SALIDA:
#   asg_{NOMBRE}_ocupados_{clave}.parquet   largo: fecha, [por], clave, descripcion,
#                                            ocupados, var_anual_pct
#   asg_{NOMBRE}_ocupados_{clave}.csv       el mismo panel largo en CSV
#   asg_{NOMBRE}_ocupados_{clave}_ancho.csv una fila por fecha [y por], una columna por clave
# ==============================================================================

import argparse
import sys
from pathlib import Path

import polars as pl

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
from extraer_asg import cargar_config  # noqa: E402
CAT_ACTIVIDADES = RAIZ / "catalogos" / "actividades_imss.csv"
CAT_ENTIDADES = RAIZ / "catalogos" / "entidades_imss.csv"


def descripciones(clave):
    """Tabla clave -> descripcion según el nivel pedido (o None si no hay catálogo)."""
    if clave.startswith("sector_economico_"):
        cat = pl.read_csv(CAT_ACTIVIDADES)
        return (cat.filter(pl.col("nivel") == clave)
                   .unique("clave", keep="first")
                   .select(pl.col("clave").cast(pl.Int32), "descripcion"))
    if clave == "cve_entidad":
        return pl.read_csv(CAT_ENTIDADES).select(
            pl.col("cve_entidad").cast(pl.Int32).alias("clave"), pl.col("entidad").alias("descripcion"))
    return None


def main():
    ap = argparse.ArgumentParser(description="Panel de personas ocupadas por clave (ASG IMSS).")
    ap.add_argument("config", help="archivo de configuración, p. ej. configs/autopartes.py")
    ap.add_argument("--clave", help="variable que define la clave (default: PANEL_CLAVE del config)")
    ap.add_argument("--por", nargs="*", help="desagregaciones extra, p. ej. cve_entidad sexo")
    ap.add_argument("--metrica", help="métrica a sumar (default: PANEL_METRICA del config, 'ta')")
    args = ap.parse_args()

    cfg = cargar_config(args.config)
    clave = args.clave or cfg["PANEL_CLAVE"]
    por = args.por if args.por is not None else list(cfg["PANEL_POR"])
    metrica = args.metrica or cfg["PANEL_METRICA"]

    carpeta = Path(cfg["CARPETA_SALIDA"]).expanduser()
    ruta_det = carpeta / f"asg_{cfg['NOMBRE']}_detalle.parquet"
    if not ruta_det.exists():
        sys.exit(f"No existe {ruta_det}. Corre antes: python extraer_asg.py {args.config}")

    det = pl.scan_parquet(ruta_det)
    cols = det.collect_schema().names()
    faltan = [c for c in [clave, metrica, *por] if c not in cols]
    if faltan:
        sys.exit(f"Columnas que no existen en el detalle: {faltan}. Disponibles: {cols}")

    # Suma por fecha x [por] x clave
    pan = (det.group_by(["fecha", *por, clave])
              .agg(pl.col(metrica).sum().alias("ocupados"))
              .rename({clave: "clave"})
              .collect())

    # Panel balanceado: toda clave en toda fecha (ceros si no hubo registros ese mes)
    malla = pan.select("fecha").unique().join(pan.select([*por, "clave"]).unique(), how="cross")
    pan = malla.join(pan, on=["fecha", *por, "clave"], how="left").with_columns(
        pl.col("ocupados").fill_null(0))

    # Variación anual (%) contra el mismo mes del año anterior
    previo = pan.select(pl.col("fecha").dt.offset_by("1y").dt.month_end().alias("fecha"),
                        *por, "clave", pl.col("ocupados").alias("ocupados_hace_1a"))
    pan = (pan.join(previo, on=["fecha", *por, "clave"], how="left")
              .with_columns(var_anual_pct=pl.when(pl.col("ocupados_hace_1a") > 0)
                            .then((pl.col("ocupados") / pl.col("ocupados_hace_1a") - 1) * 100))
              .drop("ocupados_hace_1a"))

    # Descripción de la clave y nombre de entidad si se desagrega por entidad
    desc = descripciones(clave)
    if desc is not None:
        pan = pan.with_columns(pl.col("clave").cast(pl.Int32)).join(desc, on="clave", how="left")
    else:
        pan = pan.with_columns(descripcion=pl.lit(None, pl.Utf8))
    if "cve_entidad" in por:
        ent = descripciones("cve_entidad").rename({"clave": "cve_entidad", "descripcion": "entidad"})
        pan = pan.join(ent, on="cve_entidad", how="left")

    orden = ["fecha", *por] + (["entidad"] if "cve_entidad" in por else []) + \
            ["clave", "descripcion", "ocupados", "var_anual_pct"]
    pan = pan.select(orden).sort(["fecha", *por, "clave"])

    base = carpeta / f"asg_{cfg['NOMBRE']}_ocupados_{clave}"
    pan.write_parquet(base.with_suffix(".parquet"))
    pan.write_csv(base.with_suffix(".csv"))
    ancho = (pan.with_columns(pl.col("clave").cast(pl.Utf8))
                .pivot(on="clave", index=["fecha", *por], values="ocupados")
                .sort(["fecha", *por]))
    ancho.write_csv(f"{base}_ancho.csv")

    sin_desc = pan.filter(pl.col("descripcion").is_null())["clave"].unique().to_list()
    print(f"Panel de ocupados ({metrica}) por {clave}"
          + (f" y {', '.join(por)}" if por else "")
          + f": {pan['fecha'].n_unique()} meses, {pan['clave'].n_unique()} claves, {pan.height:,} filas.")
    if desc is not None and sin_desc:
        print(f"AVISO: claves sin descripción en el catálogo: {sorted(sin_desc)}")
    print(f"  {base.with_suffix('.parquet')}\n  {base.with_suffix('.csv')}\n  {base}_ancho.csv")


if __name__ == "__main__":
    main()
