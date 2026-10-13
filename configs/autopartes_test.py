# Prueba: fracciones de autopartes solo de 2026 (corre rápido; usar con correr_test.py)
from datetime import date

NOMBRE = "autopartes_test"
CARPETA_SALIDA = "data"

FECHA_INI = date(2026, 1, 1)
FECHA_FIN = None                  # hasta el último mes cerrado

SECTOR_1 = False
SECTOR_2 = False
SECTOR_4 = [3802, 3803, 3809, 3810, 3804]
NIVEL_SECTOR = "auto"

ENTIDADES = False
SEXO = False

ETIQUETAS = {
    "nivel": "SECTOR_4",
    "grupos": {
        "autopartes": [3802, 3803, 3809, 3810],
        "sistemas_electricos": [3804],
    },
}

AGREGAR_POR = ["fecha", "grupo", "SECTOR", "ENTIDADES", "SEXO"]
METRICAS_PANEL = ["asegurados", "ta", "tpu", "teu", "masa_sal_ta"]

PANEL_CLAVE = "SECTOR"
PANEL_POR = []
PANEL_METRICA = "ta"
