# Game Frame Budget 🎮⏱️

Encuentra escenas que se salen de tu presupuesto de fotograma y compara el rendimiento de dos capturas antes de publicar una versión de tu juego. Genera informes **JSON y HTML locales**, con percentiles de tiempos, FPS efectivos y rachas de fotogramas lentos.

Creado el **29 de octubre de 2026**. Código original, capturas ficticias propias. **Python 3.10+**, sin paquetes externos, APIs, claves ni servicios.

## Instalación y demo

```bash
git clone https://github.com/alvaroalcalaa/game-frame-budget.git
cd game-frame-budget
python frame_budget.py examples/current.json --baseline examples/baseline.json --target-fps 60 --json report.json --html report.html
```

Abre `report.html` en el navegador. El mismo JSON se imprime en la terminal; `report.json` contiene el detalle completo. En la demo del prototipo ficticio Bruma:

| Escena | p95 base | p95 actual | Diferencia | Fuera de presupuesto base → actual |
|---|---:|---:|---:|---:|
| bosque | 14 ms | 14 ms | 0 ms | 2,5 % → 2,5 % |
| mercado | 16 ms | 20 ms | +4 ms | 2,5 % → 100 % |

A 60 FPS el presupuesto es aproximadamente 16,667 ms. El mercado empeora en esta captura sintética; esto **no demuestra una causa ni una regresión estadísticamente significativa**. La demo incluye una segunda visita al bosque para comprobar que las rachas se cortan entre visitas.

```bash
# Una sola captura, con un objetivo diferente
python frame_budget.py examples/current.json --target-fps 30
# Pruebas automatizadas
python -m unittest -v
```

## Datos de entrada

Exporta los tiempos de fotograma desde tu profiler o registro y conviértelos al siguiente formato. Cada elemento representa un fotograma completo; `ms` es su duración, no un timestamp. Conserva el orden de la captura:

```json
{
  "frames": [
    {"scene": "mercado", "ms": 15.5},
    {"scene": "mercado", "ms": 23.0},
    {"scene": "bosque", "ms": 13.2}
  ]
}
```

Se admite de 1 a 200000 fotogramas, hasta 200 escenas distintas y archivos de hasta 16 MiB. Los nombres de escena son textos no vacíos de hasta 120 caracteres, comparados literalmente (distinguen mayúsculas). Cada duración debe ser finita, mayor que cero y como máximo 60000 ms. Los booleanos, claves JSON repetidas y números no finitos se rechazan. Otros campos se ignoran.

No se incluye un adaptador para Unity, Unreal, Godot, PresentMon ni otro profiler. El formato permite importar datos propios mediante una transformación; **esa integración externa no está probada**. Si hay varias capturas, ejecútalas por separado: concatenarlas sin marcar transiciones puede unir rachas que no son consecutivas.

## Métricas y decisiones de cálculo

| Campo JSON | Definición |
|---|---|
| `duration_ms` | Suma de los tiempos suministrados; no es una medición adicional de tiempo de pared |
| `mean_ms` | Media aritmética del tiempo de fotograma |
| `effective_fps` | 1000 / media de ms; equivale a frames / duración total en segundos |
| `p50_ms`, `p95_ms`, `p99_ms` | Percentil por rango más próximo: ordenar y tomar el elemento `ceil(p·n/100)`, contando desde 1 |
| `slowest_1pct_mean_fps` | 1000 / media de los `ceil(n·0.01)` fotogramas más lentos, con al menos uno |
| `over_budget_frames`, `over_budget_pct` | Fotogramas con duración estrictamente superior a `1000 / target_fps` |
| `over_2x_budget_frames` | Fotogramas estrictamente por encima del doble del presupuesto |
| `longest_over_budget_run` | Máxima racha fuera de presupuesto; termina con un frame dentro de presupuesto **o con un cambio de escena**, también en el resumen global |
| `small_sample` | Verdadero con menos de 100 frames; los percentiles altos son poco representativos |

El resumen global y cada escena se calculan sobre sus propios fotogramas. Las visitas a una misma escena se agregan para medias y percentiles; las rachas respetan las transiciones originales. El indicador del 1 % es la definición explícita de este proyecto: no debe confundirse con métricas de otros profilers que usen otra fórmula.

Con `--baseline`, ambas capturas usan el mismo presupuesto. Se comparan escenas con el mismo nombre: `p95_delta_ms` y `over_budget_delta_pp` son **actual menos base**; un incremento de 20 % a 30 % es +10 puntos porcentuales. Las escenas presentes solo en una captura se indican como `added` o `removed`. El JSON conserva el número de fotogramas de cada captura para ayudar a valorar comparaciones desiguales. El HTML resume escenas actuales y muestra las diferencias; el JSON incluye todas las métricas.

## Límites y comprobaciones

Es análisis descriptivo: no identifica si el cuello de botella es CPU, GPU, carga de recursos o sincronización. Tampoco estima latencia de entrada, pérdida de frames no registrados ni fluidez percibida. Para comparaciones reales mantén hardware, configuración, recorrido y condiciones equivalentes, realiza varias capturas y revisa los datos de origen. Una escena con muestras diferentes puede cambiar por la composición de la captura.

Los informes incluyen los nombres de escena que proporciones. El HTML escapa esos textos, funciona sin red y no carga scripts externos. No se envían datos a servicios. Las salidas indicadas se reemplazan si existen; se impide sobrescribir entradas y usar la misma ruta para JSON y HTML.

Códigos de salida: **0** análisis generado; **2** argumentos, entrada o escritura incorrectos. No hay umbral automático de aprobación: una captura lenta también termina con 0. Las pruebas cubren fórmulas con resultados conocidos, comparaciones, límites, entradas inválidas, escape HTML y ejecución real de la CLI. Solo se han ejecutado sobre datos sintéticos locales.

## Licencia

MIT, incluida en `LICENSE`.
