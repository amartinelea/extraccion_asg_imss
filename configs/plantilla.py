# ==============================================================================
# PLANTILLA de configuración para extraer_asg.py
# Copia este archivo (p. ej. configs/mi_sector.py), cambia lo que necesites y corre:
#     python extraer_asg.py configs/mi_sector.py
#
# Códigos de actividad, entidades, rangos, etc.: catalogos/diccionario_IMSS.xlsx
# ==============================================================================
from datetime import date

# Nombre de la extracción. Define las carpetas y archivos de salida:
#   {CARPETA_SALIDA}/asg_{NOMBRE}_meses/      un parquet filtrado por mes (caché)
#   {CARPETA_SALIDA}/asg_{NOMBRE}_detalle.parquet
#   {CARPETA_SALIDA}/asg_{NOMBRE}_mensual.parquet
NOMBRE = "plantilla"
CARPETA_SALIDA = "data"           # puede ser absoluta, p. ej. "~/Desktop/ATDT/mi_proyecto/input/raw"

# Periodo (cortes al último día de cada mes)
FECHA_INI = date(2018, 1, 1)
FECHA_FIN = None                  # None = último mes cerrado; o p. ej. date(2025, 12, 1)

# FILTROS
# False = no filtrar esa variable. Lista = quedarse solo con esos valores.
# Entre variables se combinan con Y; dentro de una lista es O.
FILTROS = {
    # Actividad económica (catálogo IMSS; hojas "sector 1", "sector 2", "sector 4")
    "sector_economico_1": False,  # división, 1 posición: 0..9 (p. ej. [3] manufactura 3)
    "sector_economico_2": False,  # grupo, 2 posiciones (p. ej. [38] equipo de transporte)
    "sector_economico_4": False,  # fracción, 4 posiciones (p. ej. [3803, 3809])

    # Geografía
    "cve_entidad": False,         # p. ej. [11, 14] Guanajuato y Jalisco (catálogo IMSS)
    "cve_municipio": False,       # alfanumérico, p. ej. ["A01", "H83"]
    "cve_delegacion": False,
    "cve_subdelegacion": False,

    # Características
    "sexo": False,                # 1 hombre, 2 mujer
    "tamano_patron": False,       # ["S1", ..., "S7"]
    "rango_edad": False,          # ["E1", ..., "E14"]
    "rango_salarial": False,      # ["W1", ...] en salarios mínimos
    "rango_uma": False,           # ["W1", ...] en UMAs (desde feb-2017)
    "ptpd": False,                # 1 = trabajador de plataforma digital
}

# ETIQUETAS (opcional): crea una columna "grupo" agrupando valores de una variable.
# Lo que no caiga en ningún grupo queda como "otros". None = no crear la columna.
ETIQUETAS = None
# ETIQUETAS = {
#     "nivel": "sector_economico_4",
#     "grupos": {"grupo_a": [3803, 3809], "grupo_b": [3804]},
# }

# PANEL: variables por las que se agrega y métricas que se suman.
# Si incluyes "masa_sal_ta" y "ta", agrega salario_diario_prom = masa_sal_ta / ta.
AGREGAR_POR = ["fecha", "sector_economico_4", "cve_entidad", "sexo"]
METRICAS_PANEL = ["asegurados", "ta", "tpu", "teu", "tec", "tpc", "masa_sal_ta", "masa_sal_tpu"]

# Descarga
N_HILOS = 4                       # descargas simultáneas
TIMEOUT_SIN_DATOS = 60            # seg sin recibir nada antes de cortar
MAX_SEG_INTENTO = 180             # tope por intento (un mes normal tarda ~30 s)
REINTENTOS = 5
