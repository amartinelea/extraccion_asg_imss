# Ejemplo de archivo opcional: reemplaza solo estos parámetros del bloque de
# extraer_asg.py; todo lo demás se toma de ahí.
#   python extraer_asg.py configs/ejemplo_grupo38_por_estado.py
#   python panel_ocupados.py configs/ejemplo_grupo38_por_estado.py
from datetime import date

NOMBRE = "grupo38_estados"
FECHA_INI = date(2024, 1, 1)

SECTOR_2 = [38]                   # todo el grupo 38 (todas sus fracciones)
SECTOR_4 = False
ETIQUETAS = None

AGREGAR_POR = ["fecha", "SECTOR", "ENTIDADES"]
PANEL_POR = ["ENTIDADES"]         # panel de ocupados del 38 por estado
