# ==============================================================================
# PLANTILLA de configuración para extraer_asg.py y panel_ocupados.py
# Copia este archivo (p. ej. configs/mi_sector.py), cambia lo que necesites y corre:
#     python extraer_asg.py configs/mi_sector.py
#     python panel_ocupados.py configs/mi_sector.py
#
# Códigos de actividad, entidades, rangos, etc.: catalogos/diccionario_IMSS.xlsx
# (o catalogos/actividades_imss.csv y catalogos/entidades_imss.csv)
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

# ------------------------------------------------------------------------------
# FILTROS: cada uno es un vector de claves, o False para "apagarlo" (no filtrar).
# Entre filtros se combinan con Y; dentro de un vector es O.
# ------------------------------------------------------------------------------

# Actividad económica (catálogo IMSS: división > grupo > fracción; no hay nivel de 3)
SECTOR_1 = False                  # división, 1 posición: 0..9        p. ej. [3]
SECTOR_2 = False                  # grupo, 2 posiciones               p. ej. [38]
SECTOR_4 = False                  # fracción, 4 posiciones            p. ej. [3803, 3809]
# (FRACCIONES = [...] también funciona como sinónimo de SECTOR_4)

# Geografía
ENTIDADES = False                 # p. ej. [11, 14] Guanajuato y Jalisco
MUNICIPIOS = False                # alfanumérico IMSS, p. ej. ["A01", "H83"]
DELEGACIONES = False
SUBDELEGACIONES = False

# Características del puesto y del trabajador
SEXO = False                      # 1 hombre, 2 mujer
TAMANO_PATRON = False             # ["S1", ..., "S7"]
RANGO_EDAD = False                # ["E1", ..., "E14"]
RANGO_SALARIAL = False            # ["W1", ...] en salarios mínimos
RANGO_UMA = False                 # ["W1", ...] en UMAs (desde feb-2017)
PLATAFORMA_DIGITAL = False        # [1] = trabajadores de plataformas digitales

# ------------------------------------------------------------------------------
# ETIQUETAS (opcional): crea una columna "grupo" agrupando claves de un nivel.
# Lo que no caiga en ningún grupo queda como "otros". None = no crear la columna.
# ------------------------------------------------------------------------------
ETIQUETAS = None
# ETIQUETAS = {
#     "nivel": "SECTOR_4",
#     "grupos": {"grupo_a": [3803, 3809], "grupo_b": [3804]},
# }

# ------------------------------------------------------------------------------
# PANEL AGREGADO (asg_{NOMBRE}_mensual.parquet)
# Se puede usar el nombre del parámetro ("SECTOR_4", "ENTIDADES") o la columna del
# ASG ("sector_economico_4", "cve_entidad"). Si incluyes "masa_sal_ta" y "ta",
# agrega salario_diario_prom = masa_sal_ta / ta.
# ------------------------------------------------------------------------------
AGREGAR_POR = ["fecha", "SECTOR_4", "ENTIDADES", "SEXO"]
METRICAS_PANEL = ["asegurados", "ta", "tpu", "teu", "tec", "tpc", "masa_sal_ta", "masa_sal_tpu"]

# ------------------------------------------------------------------------------
# PANEL DE OCUPADOS (panel_ocupados.py): fecha x clave, sumando PANEL_METRICA.
# PANEL_CLAVE:   "SECTOR_1", "SECTOR_2", "SECTOR_4", "grupo" (si hay ETIQUETAS),
#                "ENTIDADES", etc.
# PANEL_POR:     desagregaciones extra, p. ej. ["ENTIDADES"] o ["SEXO"]; [] = nacional
# PANEL_METRICA: "ta" (puestos de trabajo afiliados) o "asegurados", "tpu", "teu", ...
# ------------------------------------------------------------------------------
PANEL_CLAVE = "SECTOR_4"
PANEL_POR = []
PANEL_METRICA = "ta"

# Descarga
N_HILOS = 4                       # descargas simultáneas
TIMEOUT_SIN_DATOS = 60            # seg sin recibir nada antes de cortar
MAX_SEG_INTENTO = 180             # tope por intento (un mes normal tarda ~30 s)
REINTENTOS = 5
