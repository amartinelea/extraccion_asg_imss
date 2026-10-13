# ==============================================================================
# Prueba de punta a punta: corre extraer_asg.py y panel_ocupados.py con
# configs/autopartes_test.py (fracciones de autopartes, solo 2026) y valida salidas.
#
# Uso (desde la raíz del repo):
#   python correr_test.py
#   python correr_test.py --comparar ~/Desktop/ATDT/proyecto_autopartes/input/raw/asg
#       compara además contra meses ya descargados con el script del proyecto
#   python correr_test.py --limpiar     borra antes las salidas de una prueba anterior
# ==============================================================================

import argparse
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import polars as pl

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
from extraer_asg import cargar_config, fechas_corte, ruta_salida  # noqa: E402

CONFIG = RAIZ / "configs" / "autopartes_test.py"

resultados = []


def revisa(nombre, ok, detalle=""):
    resultados.append(ok)
    print(f"  [{'OK' if ok else 'FALLA'}] {nombre}" + (f": {detalle}" if detalle else ""))


def correr(script, *extra):
    print(f"\n$ python {script} {CONFIG.relative_to(RAIZ)} {' '.join(extra)}")
    r = subprocess.run([sys.executable, str(RAIZ / script), str(CONFIG), *extra], cwd=RAIZ)
    revisa(f"{script} terminó sin error", r.returncode == 0, f"código {r.returncode}")
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comparar", help="carpeta con asg_AAAA-MM-DD.parquet del proyecto de autopartes")
    ap.add_argument("--limpiar", action="store_true", help="borra salidas previas de la prueba")
    args = ap.parse_args()

    cfg = cargar_config(CONFIG)
    salida = ruta_salida(cfg)
    nombre = cfg["NOMBRE"]
    fracciones = sorted(cfg["FILTROS"]["sector_economico_4"])

    if args.limpiar:
        shutil.rmtree(salida / f"asg_{nombre}_meses", ignore_errors=True)
        for f in salida.glob(f"asg_{nombre}_*"):
            f.unlink()

    # 1. Correr ambos scripts ____________________________________________________
    if not correr("extraer_asg.py"):
        sys.exit("extraer_asg.py falló; no tiene caso seguir.")
    correr("panel_ocupados.py")

    print("\nValidaciones")
    det = pl.read_parquet(salida / f"asg_{nombre}_detalle.parquet")
    pan = pl.read_parquet(salida / f"asg_{nombre}_mensual.parquet")
    ocu = pl.read_parquet(salida / f"asg_{nombre}_ocupados_sector_economico_4.parquet")

    # 2. Meses ___________________________________________________________________
    esperados = [date.fromisoformat(f) for f in fechas_corte(cfg["FECHA_INI"], cfg["FECHA_FIN"])]
    tiene = sorted(det["fecha"].unique().to_list())
    faltan = [f for f in esperados if f not in tiene]
    huecos = [f for f in faltan if f < max(tiene)] if tiene else faltan
    revisa("hay meses descargados", len(tiene) > 0, f"{len(tiene)} de {len(esperados)}")
    revisa("sin huecos entre meses", not huecos,
           f"faltan {[str(f) for f in huecos]}" if huecos else "")
    if faltan and not huecos:
        print(f"  [AVISO] el IMSS aún no publica: {[str(f) for f in faltan]}")

    # 3. Filtro de fracciones ________________________________________________________
    vistas = sorted(det["sector_economico_4"].unique().to_list())
    revisa("solo las fracciones pedidas", vistas == fracciones, f"{vistas}")
    por_mes = det.group_by("fecha").agg(pl.col("sector_economico_4").n_unique().alias("n"))
    incompletos = por_mes.filter(pl.col("n") < len(fracciones))["fecha"].to_list()
    revisa(f"las {len(fracciones)} fracciones en todos los meses", not incompletos,
           f"{[str(f) for f in incompletos]}" if incompletos else "")

    # 4. Etiquetas ___________________________________________________________________
    g = det.group_by("grupo").agg(pl.col("sector_economico_4").unique().sort()).sort("grupo")
    mapa = {r["grupo"]: r["sector_economico_4"] for r in g.to_dicts()}
    revisa("etiquetas correctas",
           mapa == {"autopartes": [3802, 3803, 3809, 3810], "sistemas_electricos": [3804]}, f"{mapa}")

    # 5. Consistencia de totales ____________________________________________________
    t_det = det.group_by("fecha").agg(pl.col("ta").sum()).sort("fecha")
    t_pan = pan.group_by("fecha").agg(pl.col("ta").sum()).sort("fecha")
    t_ocu = ocu.group_by("fecha").agg(pl.col("ocupados").sum()).sort("fecha")
    revisa("panel agregado = detalle (ta por mes)", t_det.equals(t_pan))
    revisa("panel de ocupados = detalle (ta por mes)",
           t_det["ta"].round(2).to_list() == t_ocu["ocupados"].round(2).to_list())

    # 6. Panel de ocupados _______________________________________________________________
    revisa("ocupados > 0 en todas las celdas", ocu.filter(pl.col("ocupados") <= 0).height == 0,
           f"{ocu.filter(pl.col('ocupados') <= 0).height} celdas en cero")
    revisa("todas las claves tienen descripción", ocu["descripcion"].null_count() == 0)
    revisa("panel balanceado (meses x fracciones)",
           ocu.height == len(tiene) * len(fracciones), f"{ocu.height} filas")
    ancho = salida / f"asg_{nombre}_ocupados_sector_economico_4_ancho.csv"
    revisa("CSV ancho existe", ancho.exists())

    # 7. Comparación contra el proyecto (opcional) _______________________________________
    if args.comparar:
        carpeta = Path(args.comparar).expanduser()
        archivos = [carpeta / f"asg_{f.isoformat()}.parquet" for f in tiene]
        archivos = [a for a in archivos if a.exists()]
        if not archivos:
            print(f"  [AVISO] no hay meses de 2026 en {carpeta} para comparar")
        else:
            ref = pl.concat([pl.read_parquet(a) for a in archivos], how="diagonal_relaxed")
            ref = (ref.with_columns(pl.col("sector_economico_4").cast(pl.Int32),
                                    pl.col("ta").cast(pl.Float64), pl.col("fecha").cast(pl.Date))
                      .group_by(["fecha", "sector_economico_4"]).agg(pl.col("ta").sum()))
            nuevo = det.group_by(["fecha", "sector_economico_4"]).agg(pl.col("ta").sum())
            cmp = ref.join(nuevo, on=["fecha", "sector_economico_4"], how="full",
                           suffix="_nuevo", coalesce=True)
            difs = cmp.filter((pl.col("ta") - pl.col("ta_nuevo")).abs().fill_null(1) > 0.5)
            revisa(f"igual al proyecto en {len(archivos)} meses", difs.height == 0,
                   f"{difs.height} diferencias" if difs.height else "")

    # Resumen ________________________________________________________________________
    print(f"\nResumen ocupados (ta) por fracción, último mes {max(tiene)}:")
    print(ocu.filter(pl.col("fecha") == max(tiene))
             .select("clave", pl.col("descripcion").str.slice(0, 60), "ocupados"))
    n_falla = resultados.count(False)
    print(f"\n{'TODO BIEN' if n_falla == 0 else f'{n_falla} VALIDACIONES FALLARON'} "
          f"({resultados.count(True)} de {len(resultados)} OK)")
    sys.exit(1 if n_falla else 0)


if __name__ == "__main__":
    main()
