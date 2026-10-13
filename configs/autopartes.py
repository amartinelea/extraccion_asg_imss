# Autopartes y sistemas eléctricos automotrices (catálogo IMSS, grupo 38)
#   3802 carrocerías; 3803 partes y accesorios; 3809 motores; 3810 conjuntos mecánicos
#   3804 partes para el sistema eléctrico de vehículos
from datetime import date

NOMBRE = "autopartes"
CARPETA_SALIDA = "data"

FECHA_INI = date(2018, 1, 1)
FECHA_FIN = None

FILTROS = {
    "sector_economico_1": False,
    "sector_economico_2": False,
    "sector_economico_4": [3802, 3803, 3809, 3810, 3804],
    "cve_entidad": False,
    "sexo": False,
}

ETIQUETAS = {
    "nivel": "sector_economico_4",
    "grupos": {
        "autopartes": [3802, 3803, 3809, 3810],
        "sistemas_electricos": [3804],
    },
}

AGREGAR_POR = ["fecha", "grupo", "sector_economico_4", "cve_entidad", "sexo"]
METRICAS_PANEL = ["asegurados", "ta", "teu", "tec", "tpu", "tpc", "masa_sal_ta", "masa_sal_tpu"]

# PANEL DE OCUPADOS (panel_ocupados.py): fecha x clave, sumando PANEL_METRICA.
# PANEL_CLAVE: "sector_economico_1", "sector_economico_2", "sector_economico_4",
#              "grupo" (si hay ETIQUETAS), "cve_entidad", etc.
# PANEL_POR:   desagregaciones extra, p. ej. ["cve_entidad"] o ["sexo"]; [] = total nacional
# PANEL_METRICA: "ta" (puestos de trabajo afiliados) o "asegurados", "tpu", "teu", ...
PANEL_CLAVE = "sector_economico_4"
PANEL_POR = []
PANEL_METRICA = "ta"
