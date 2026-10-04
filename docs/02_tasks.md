# Pipeline de tareas — Agente de limpieza Dalefon

Leyenda: 🔒 = bloqueado por decisión pendiente · Resp. = responsable

## Fase 0 — Entorno (≈0,5 día)
| # | Tarea | Resultado | Resp. |
|---|---|---|---|
| 0.1 | Crear estructura del repo + `git init` + entorno virtual Python | Repo listo | Claude |
| 0.2 | Instalar pandas, duckdb, kaggle, google-cloud-bigquery | `requirements.txt` | Claude |
| 0.3 | Generar token de Kaggle y guardarlo en `~/.kaggle/kaggle.json` | Acceso a Kaggle | **Tú** |
| 0.4 | Instalar Google Cloud SDK (`gcloud`) y hacer login | CLI autenticada | **Tú** |

## Fase 1 — Datos (≈1 día)
| # | Tarea | Resultado |
|---|---|---|
| 1.1 | Descargar dataset prepago (~100k × 226) y verificar filas/columnas reales | `data/raw/` |
| 1.2 | Perfilado inicial: nulos, tipos, rangos, duplicados, columnas constantes | Informe de suciedad nativa |
| 1.3 | Añadir columnas sintéticas tipo Dalefon (teléfono MX, email, IMEI, modelo) | Esquema cliente + consumo |
| 1.4 | Inyector de errores reproducible (semilla fija) + fichero de verdad (*ground truth*) | `data/dirty/` + `ground_truth.csv` |

## Fase 2 — Agente en local (≈4–5 días)
| # | Tarea | Resultado |
|---|---|---|
| 2.1 | **Profile**: estadísticas por columna en SQL (DuckDB local = mismo SQL que BigQuery) | `profile.json` |
| 2.2 | **Detect**: reglas deterministas (formato, rango, Luhn IMEI, unicidad) | Lista de incidencias |
| 2.3 | **Detect semántico**: LLM recibe perfil + muestra enmascarada → identifica tipo de columna y anomalías 🔒 LLM | Incidencias semánticas |
| 2.4 | **Plan**: LLM propone acciones en JSON + SQL de corrección | `cleaning_plan.json` |
| 2.5 | **Review**: aprobación humana acción por acción (CLI) | Plan aprobado |
| 2.6 | **Execute + Verify**: aplicar SQL, re-perfilar, diff antes/después | Tabla limpia |
| 2.7 | **Report**: informe de auditoría (estadísticas, visión general, errores, recomendaciones) | `audit_report.md/html` |
| 2.8 | Enmascarado de PII antes de cualquier llamada al LLM | Módulo `pii.py` |

## Fase 3 — Evaluación (≈1–2 días)
| # | Tarea | Resultado |
|---|---|---|
| 3.1 | Precisión/recall de detección vs ground truth | Métricas por tipo de error |
| 3.2 | Exactitud de reparación (% celdas restauradas al valor real) | Métrica |
| 3.3 | Baseline A: script pandas escrito a mano | Comparativa |
| 3.4 | Baseline B: BigQuery Data Preparation (Gemini nativo) | Comparativa (en fase 4) |
| 3.5 | Coste (tokens LLM + bytes BigQuery) y tiempo por ejecución | Tabla de costes |

## Fase 4 — Google Cloud (≈2 días) 🔒 proyecto GCP
| # | Tarea | Resultado |
|---|---|---|
| 4.1 | Proyecto + facturación + alerta de presupuesto | Proyecto activo |
| 4.2 | Activar APIs: BigQuery, Cloud Storage, Vertex AI, Cloud Run | APIs listas |
| 4.3 | Bucket `raw` + datasets BigQuery `bronze` / `silver` / `gold` | Infraestructura |
| 4.4 | Cuenta de servicio: solo lectura en `bronze`, escritura en `silver`/`gold` (simula acceso de Dalefon) | IAM mínimo |
| 4.5 | Cargar CSV sucio a GCS → `bronze` | Datos en la nube |
| 4.6 | Cambiar el motor del agente de DuckDB a BigQuery | Agente en GCP |
| 4.7 | Empaquetar como Cloud Run Job y ejecutarlo | Ejecución en la nube |

## Fase 5 — Resultados (≈1–2 días)
| # | Tarea | Resultado |
|---|---|---|
| 5.1 | Revisar datos transformados en `silver`/`gold` | Validación |
| 5.2 | Dashboard Looker Studio: calidad antes/después + datos limpios | Dashboard |
| 5.3 | Documento de investigación: método, métricas, conclusiones | Informe final |
| 5.4 | Plantilla de auditoría lista para los datos reales de Dalefon | Entregable cliente |

**Total estimado: ~10–13 días de trabajo** (suposición, no medido).

## Decisiones pendientes
- 🔒 LLM: Gemini en Vertex AI (recomendado) / Claude en Vertex AI → bloquea 2.3
- 🔒 Proyecto GCP: propio / sandbox Dalefon → bloquea fase 4
- Idioma de entregables → afecta 2.7 y 5.3
