# llama.cpp: benchmark local de generación de código

Resultados de cinco modelos GGUF ejecutados localmente el **23 de octubre de 2026**. Se comparó la generación normal (`Base`) con decodificación especulativa `MTP4`, `DFlash8` o `Ngram16`, según el modelo. Estos son resultados de una máquina y un conjunto pequeño de problemas; no son una clasificación general de modelos.

## Resumen de velocidad

Cada cifra es la **mediana de 15 respuestas** (cinco problemas × tres repeticiones) de `tokens_per_second` en la corrida indicada. La razón compara medianas del mismo modelo y corrida. Las 15 solicitudes de cada modo terminaron con estado `OK`; ese estado solo indica que la API devolvió una respuesta.

| Modelo GGUF | Corrida | Base tok/s | Modo alternativo tok/s | Razón alternativa/Base |
|---|---|---:|---:|---:|
| Qwen3.5-9B Q6_K_L | `20261023_014253` | 74.02 | MTP4: 111.48 | 1.51× |
| Qwen3.5-9B Q6_K_L | `20261023_014253` | 74.02 | DFlash8: 219.11 | 2.96× |
| Gemma-3-4B-it Q4_K_M | `gemma3_20261023_020806` | 160.54 | Ngram16: 160.63 | 1.00× |
| Underdog-Saluki-27B IQ2-mix | `saluki27_20261023_021622` | 49.75 | Ngram16: 48.69 | 0.98× |
| Ornith-1.5-9B-heretic Q6_K | `ornith9_20261023_022403` | 80.24 | Ngram16: 79.68 | 0.99× |
| Qwen3.8-9B-Distill Q4_K_M | `qwen38_20261023_024526` | 99.53 | Ngram16: 98.62 | 0.99× |

**Lectura:** DFlash8 fue claramente más rápido en esta corrida de Qwen3.5. Ngram16 no mostró una mejora consistente en las otras cuatro corridas. Las salidas tienen longitudes distintas; la razón de medianas de velocidad no equivale a reducción de tiempo para una tarea de contenido idéntico.

## Pruebas funcionales

Después de generar código se ejecutaron pruebas locales. Las cifras son casos aprobados sobre 72 por modo: cinco problemas, tres respuestas por problema y varios casos por respuesta. `ERROR` (por ejemplo, una excepción al ejecutar el código) y `FAIL` (una aserción incorrecta) cuentan como no aprobados.

| Modelo / corrida principal | Base | Modo alternativo |
|---|---:|---:|
| Qwen3.5-9B / `20261023_014253` | 42/72 | MTP4: 55/72; DFlash8: 39/72 |
| Gemma-3-4B-it / `gemma3_20261023_020806` | 41/72 | Ngram16: 41/72 |
| Underdog-Saluki-27B / `saluki27_20261023_021622` | 54/72 | Ngram16: 54/72 |
| Ornith-1.5-9B-heretic / `ornith9_20261023_022403` | 18/72 | Ngram16: 18/72 |
| Qwen3.8-9B-Distill / `qwen38_20261023_024526` | 33/72 | Ngram16: 33/72 |

Estos resultados funcionales no demuestran una mejora de calidad causada por la decodificación. Es una muestra de tres generaciones por modo. En varios casos las respuestas fallaron por errores de código, incluidos imports ausentes. Para ver `PASS`, `FAIL`, `ERROR`, `TIMEOUT` y `MISSING` por problema, consulte [`functional_summary.csv`](functional_summary.csv).

## Corridas complementarias

| Modelo | Corrida | Modo | Mediana tok/s | Pruebas funcionales |
|---|---|---|---:|---:|
| Ornith-1.5-9B-heretic | `ornith_ttl_repeat_20261023_023418` | Base | 79.20 (5 respuestas TTL) | No registradas |
| Qwen3.8-9B-Distill | `qwen38_mtp_20261023_025031` | Base / MTP4 / Ngram16 | 127.99 / 125.77 / 127.98 | 36/72 en los tres modos; evaluado después sobre el código guardado |

La corrida posterior válida de Qwen3.8 es más rápida que la primera incluso en `Base`. Se conserva por separado; no se atribuye esa diferencia a MTP4 ni a Ngram16. La corrida `qwen38_mtp_20261023_025325` se inició por error al intentar generar el reporte funcional: queda excluida de las tablas y CSV publicados como benchmark. Para completar el reporte correcto se ejecutó el evaluador funcional sobre los 45 archivos de código ya guardados en `qwen38_mtp_20261023_025031`, sin volver a generar respuestas. La repetición TTL de Ornith tiene solo cinco respuestas, todas de 4096 tokens, y no es comparable con las corridas de 15 respuestas.

## Método y archivos

- Los prompts, en español, pidieron código Python 3.12 para una caché LRU, una caché TTL, Dijkstra, un parser CSV y un planificador de tareas. Se solicitaron solo código, sin explicaciones ni Markdown.
- En los scripts conservados de Gemma, Saluki, Ornith y Qwen3.8 se usó `llama-server` en `127.0.0.1:8080`, un slot (`-np 1`), contexto de 16 384 (`-c 16384`), 99 capas GPU (`-ngl 99`), Flash Attention, `temperature: 0`, `max_tokens: 4096`, `stream: false` y tres repeticiones por problema. `Ngram16` usó `--spec-type ngram-simple --spec-draft-n-max 16`. La corrida posterior de Qwen3.8 usó `MTP4` con `--spec-type draft-mtp --spec-draft-n-max 4 --spec-draft-p-min 0.75`.
- [`measurements.csv`](measurements.csv) normaliza las 215 filas de siete archivos `results.csv`, excluyendo la corrida accidental. `tokens_per_second` procede de los tiempos de generación informados por `llama-server`; `wall_time_ms` es tiempo de solicitud medido por el cliente. `generation_ms` conserva `GenerationMs` en la primera corrida y `predicted_ms` en las demás.
- [`functional_summary.csv`](functional_summary.csv) reúne 70 filas: cinco resúmenes originales y el resumen nuevo calculado sobre el código guardado de `qwen38_mtp_20261023_025031`. Para ese cálculo se usó [`functional_benchmark.py`](functional_benchmark.py) con `BENCH_RESULTS` apuntando a una copia de los 45 archivos `.py` de esa corrida. Las pruebas se ejecutaron en subprocesos con límite de cinco segundos por caso. Un archivo de respuestas generado se sometió a varios casos; esos casos comparten la misma respuesta y no son observaciones independientes.
- [`source_hashes.json`](source_hashes.json) registra SHA-256 de los 12 CSV originales usados, del resumen funcional derivado (`origin: derived_from_saved_code`) y del evaluador. Los archivos originales no se modificaron.

## Límites de interpretación y reproducción

1. No hay una identificación verificada del hardware, la versión exacta de `llama.cpp`, el controlador, la carga del sistema ni las opciones completas de la **primera** corrida de Qwen3.5. El script que la produjo no está disponible junto a los scripts conservados. Por eso su configuración DFlash8 no se presenta como receta reproducible.
2. Los cinco modelos tienen tamaños y cuantizaciones diferentes. Sus velocidades absolutas no aíslan el efecto de una técnica de decodificación.
3. Los 15 resultados por modo son solo tres respuestas por problema, con orden fijo y posibles efectos de calentamiento, caché y variación del sistema. No hay intervalos de confianza ni control de esos factores.
4. El número de tokens generados varía entre modos. Compare velocidad y tiempo de pared junto con el largo de salida en `measurements.csv`; no trate tokens/s como una medida completa de productividad o calidad.
5. El conjunto funcional es estrecho. Un `OK` de la API no implica código correcto, y aprobar estos casos tampoco garantiza corrección general. Los resúmenes no incluyen el código generado ni los mensajes de error completos.
6. No se han repetido los modelos para esta publicación. Solo se ejecutó la evaluación funcional pendiente sobre las respuestas ya guardadas de Qwen3.8. Los tiempos reflejan únicamente las corridas guardadas el 23 de octubre de 2026.
7. El resumen funcional nuevo se calculó con la versión disponible de `functional_benchmark.py`; no hay un snapshot del evaluador asociado a cada resumen anterior. La equivalencia exacta de las pruebas funcionales entre fechas de ejecución no está verificada.
