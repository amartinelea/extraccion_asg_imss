# Extracción de ASG del IMSS

Descarga los cortes mensuales de **asegurados del IMSS (ASG, datos abiertos)** y los
filtra por cualquier combinación de actividad económica, geografía y características
del trabajador. Deja un caché por mes, un archivo de detalle y un panel agregado, todo
en parquet.

## Uso

```bash
python -m pip install -r requirements.txt
python extraer_asg.py configs/autopartes.py      # 1. descarga, filtra y agrega
python panel_ocupados.py configs/autopartes.py   # 2. panel de ocupados por clave
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
| `SECTOR_1`, `SECTOR_2`, `SECTOR_4` | Actividad económica: vector de claves o `False` |
| `ENTIDADES`, `MUNICIPIOS`, `SEXO`, `TAMANO_PATRON`, `RANGO_EDAD`, … | Otros filtros: vector o `False` |
| `NIVEL_SECTOR` | Nivel al que se suman los paneles: `"auto"`, `"SECTOR_1"`, `"SECTOR_2"` o `"SECTOR_4"` |
| `ETIQUETAS` | Opcional; crea la columna `grupo` agrupando claves |
| `AGREGAR_POR`, `METRICAS_PANEL` | Cómo se arma el panel agregado |
| `PANEL_CLAVE`, `PANEL_POR`, `PANEL_METRICA` | Panel de ocupados |
| `N_HILOS`, `TIMEOUT_SIN_DATOS`, `MAX_SEG_INTENTO`, `REINTENTOS` | Descarga |

**Filtros:** cada uno es un vector de claves, o `False` para apagarlo. Entre filtros se
combinan con Y; dentro de un vector es O.

```python
SECTOR_1 = False
SECTOR_2 = False
SECTOR_4 = [3802, 3803, 3809, 3810, 3804]   # o FRACCIONES = [...]
ENTIDADES = [11, 14]                        # Guanajuato o Jalisco
```

Niveles de actividad del catálogo IMSS (no tiene nivel de 3 posiciones):

* `SECTOR_1`: división (1 posición)
* `SECTOR_2`: grupo (2 posiciones, p. ej. 38)
* `SECTOR_4`: fracción (4 posiciones, p. ej. 3803)

**Agregación automática por nivel.** Cada fila del ASG viene a nivel fracción y trae
sus claves de grupo y división, así que `SECTOR_2 = [38]` se queda con todas las
fracciones 38xx. Con `NIVEL_SECTOR = "auto"` (default), los paneles se suman al nivel
más fino que tenga filtro:

| Configuración | Panel |
|---|---|
| `SECTOR_2 = [38]` | una serie: grupo 38 (suma de todas sus fracciones) |
| `SECTOR_2 = [37, 38]` | dos series: 37 y 38 |
| `SECTOR_1 = [3]` | una serie: división 3 |
| `SECTOR_4 = [3803, 3809]` | dos series: 3803 y 3809 |
| `SECTOR_4 = [3803, 3809]` y `NIVEL_SECTOR = "SECTOR_2"` | una serie: 38 (solo esas dos fracciones) |
| sin filtros de actividad | por fracción |

En `AGREGAR_POR` y `PANEL_CLAVE`, `"SECTOR"` significa "el nivel de `NIVEL_SECTOR`".
El archivo de detalle siempre queda a nivel fracción.

Si pones `SECTOR_2` y `SECTOR_4` a la vez, el script avisa qué fracciones no caen en
los grupos pedidos (quedarían fuera). En `ETIQUETAS`, `AGREGAR_POR` y `PANEL_*` puedes
usar el nombre del parámetro (`"SECTOR_4"`, `"ENTIDADES"`) o la columna del ASG
(`"sector_economico_4"`, `"cve_entidad"`).

Los códigos de todas las variables están en `catalogos/diccionario_IMSS.xlsx`. Las
descripciones de actividades y entidades también están en CSV
(`catalogos/actividades_imss.csv`, `catalogos/entidades_imss.csv`).

## Salidas

```
{CARPETA_SALIDA}/
├── asg_{NOMBRE}_meses/            un parquet filtrado por mes + _filtros.json
├── asg_{NOMBRE}_detalle.parquet   filas originales filtradas, todos los meses
└── asg_{NOMBRE}_mensual.parquet   panel agregado según AGREGAR_POR
```

## Panel de personas ocupadas

`panel_ocupados.py` toma el detalle de una extracción y arma un panel **fecha × clave**
con las personas ocupadas, la descripción de la clave según el catálogo IMSS y la
variación anual (%). Es un panel balanceado: si una clave no tiene registros un mes,
aparece con 0.

* Por default, "ocupados" es `ta`, los puestos de trabajo afiliados (la cifra de
  empleo formal que publica el IMSS). Se cambia con `PANEL_METRICA` o `--metrica`.
* La clave se define con `PANEL_CLAVE` o `--clave`: `SECTOR` (default, el nivel de
  `NIVEL_SECTOR`), `SECTOR_1`, `SECTOR_2`, `SECTOR_4`,
  `grupo` (si hay `ETIQUETAS`), `ENTIDADES`, etc.
* Desagregaciones extra con `PANEL_POR` o `--por` (p. ej. `--por ENTIDADES SEXO`).

```bash
python panel_ocupados.py configs/autopartes.py --clave grupo
python panel_ocupados.py configs/autopartes.py --clave SECTOR_2 --por ENTIDADES
```

Salidas en `CARPETA_SALIDA`:

```
asg_{NOMBRE}_ocupados_{clave}.parquet    largo: fecha, [por], clave, descripcion, ocupados, var_anual_pct
asg_{NOMBRE}_ocupados_{clave}.csv        lo mismo en CSV
asg_{NOMBRE}_ocupados_{clave}_ancho.csv  una columna por clave
```

## Cómo funciona

* Cada CSV mensual (cientos de MB) se baja a una carpeta temporal, se filtra con polars
  y se borra. Se bajan varios meses a la vez (`N_HILOS`).
* Si se interrumpe, al volver a correr se salta los meses ya guardados.
* El servidor del IMSS a veces se cuelga o manda datos a cuentagotas: si pasa
  `TIMEOUT_SIN_DATOS` sin datos o un intento dura más de `MAX_SEG_INTENTO`, lo corta y
  reintenta. Un error 404 no se reintenta (el mes no está publicado con ese nombre).
* `_filtros.json` guarda con qué filtros se armó el caché. Si cambias algún filtro con el
  mismo `NOMBRE`, el script se detiene para no mezclar meses filtrados distinto.

## Notas

* El portal solo funciona por **http**; si el navegador te manda a https verás
  "Error 29, SSL is not supported".
* El catálogo de actividades del IMSS clasifica por riesgo de trabajo, no por producto,
  así que no tiene una equivalencia uno a uno con SCIAN.
