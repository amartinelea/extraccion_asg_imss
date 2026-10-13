# Autopartes y sistemas eléctricos automotrices (catálogo IMSS, grupo 38)
#   3802 carrocerías; 3803 partes y accesorios; 3809 motores; 3810 conjuntos mecánicos
#   3804 partes para el sistema eléctrico de vehículos
from datetime import date

NOMBRE = "autopartes"
CARPETA_SALIDA = "data"

FECHA_INI = date(2018, 1, 1)
FECHA_FIN = None

# Actividad económica: vector de claves o False para no filtrar ese nivel
SECTOR_1 = False
SECTOR_2 = False
SECTOR_4 = [3802, 3803, 3809, 3810, 3804]

# Otros filtros
ENTIDADES = False
SEXO = False

ETIQUETAS = {
    "nivel": "SECTOR_4",
    "grupos": {
        "autopartes": [3802, 3803, 3809, 3810],
        "sistemas_electricos": [3804],
    },
}

AGREGAR_POR = ["fecha", "grupo", "SECTOR_4", "ENTIDADES", "SEXO"]
METRICAS_PANEL = ["asegurados", "ta", "teu", "tec", "tpu", "tpc", "masa_sal_ta", "masa_sal_tpu"]

# Panel de ocupados (panel_ocupados.py)
PANEL_CLAVE = "SECTOR_4"
PANEL_POR = []
PANEL_METRICA = "ta"
