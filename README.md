# Extracción de ASG del IMSS

Descarga los cortes mensuales de **asegurados del IMSS (ASG, datos abiertos)** y los
filtra por cualquier combinación de actividad económica, geografía y características
del trabajador. Deja un caché por mes, un archivo de detalle y un panel agregado, todo
en parquet.

## Uso

```bash
python -m pip install -r requirements.txt
python extraer_asg.py configs/autopartes.py
```

Para una extracción nueva, copia `configs/plantilla.py`, ajusta los filtros y córrelo
igual. Con `--solo-unir` no descarga nada y solo rearma el detalle y el panel con los
meses ya guardados (útil si cambias `ETIQUETAS`, `AGREGAR_POR` o `METRICAS_PANEL`).

## Configuración

Todo vive en el archivo de `configs/`:

| Variable | Qué hace |
|---|---|
| `NOMBRE` | Nombre de la extracción; define carpetas y archivos de salida |
| `CARPETA_SALIDA` | Dónde se guarda todo (relativa o absoluta) |
| `FECHA_INI`, `FECHA_FIN` | Periodo; `FECHA_FIN = None` es el último mes cerrado |
| `FILTROS` | Un vector por variable; `False` no filtra |
| `ETIQUETAS` | Opcional; crea la columna `grupo` agrupando valores |
| `AGREGAR_POR`, `METRICAS_PANEL` | Cómo se arma el panel agregado |
| `N_HILOS`, `TIMEOUT_SIN_DATOS`, `MAX_SEG_INTENTO`, `REINTENTOS` | Descarga |

**Filtros:** entre variables se combinan con Y; dentro de un vector es O. Por ejemplo,
`sector_economico_2: [38]` con `cve_entidad: [11, 14]` da el grupo 38 en Guanajuato
o Jalisco.

Niveles de actividad del catálogo IMSS:

* `sector_economico_1`: división (1 posición)
* `sector_economico_2`: grupo (2 posiciones, p. ej. 38)
* `sector_economico_4`: fracción (4 posiciones, p. ej. 3803)

Los códigos de todas las variables están en `catalogos/diccionario_IMSS.xlsx`.

## Salidas

```
{CARPETA_SALIDA}/
├── asg_{NOMBRE}_meses/            un parquet filtrado por mes + _filtros.json
├── asg_{NOMBRE}_detalle.parquet   filas originales filtradas, todos los meses
└── asg_{NOMBRE}_mensual.parquet   panel agregado según AGREGAR_POR
```

## Cómo funciona

* Cada CSV mensual (cientos de MB) se baja a una carpeta temporal, se filtra con polars
  y se borra. Se bajan varios meses a la vez (`N_HILOS`).
* Si se interrumpe, al volver a correr se salta los meses ya guardados.
* El servidor del IMSS a veces se cuelga o manda datos a cuentagotas: si pasa
  `TIMEOUT_SIN_DATOS` sin datos o un intento dura más de `MAX_SEG_INTENTO`, lo corta y
  reintenta. Un error 404 no se reintenta (el mes no está publicado con ese nombre).
* `_filtros.json` guarda con qué filtros se armó el caché. Si cambias `FILTROS` con el
  mismo `NOMBRE`, el script se detiene para no mezclar meses filtrados distinto.

## Notas

* El portal solo funciona por **http**; si el navegador te manda a https verás
  "Error 29, SSL is not supported".
* El catálogo de actividades del IMSS clasifica por riesgo de trabajo, no por producto,
  así que no tiene una equivalencia uno a uno con SCIAN.
