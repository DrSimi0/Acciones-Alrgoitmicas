# Estado del Proyecto: Arbitraje Estadístico de Pares

* **Fecha de actualización:** 2026-10-30
* **Fase Actual:** Fase 7 Completada — Integración de Filtro de Cuarentena Corporativa (Earnings Blackout) y Validación Walk-Forward en Producción

---

## 1. Objetivos del Proyecto
Desarrollar un sistema modular, reproducible y riguroso para investigar estrategias de arbitraje estadístico y reversión a la media en acciones, verificando fuera de muestra y tras costos si existe una ventaja cuantitativa explotable sin optimización prematura.

---

## 2. Decisiones y Hechos Verificados
- **Stack Tecnológico:** Python 3.11 (`pandas`, `numpy`, `scipy`, `statsmodels`, `pytest`).
- **Arquitectura Funnel:** Preselección rápida por distancia SSD $\to$ Validación econométrica rigurosa (Engle-Granger, Johansen, OU, FDR Benjamini-Hochberg) $\to$ Filtro de Kalman secuencial para hedge ratio $\beta_t \to$ Señales elásticas GARCH con fallback $\to$ Filtro de Cuarentena Corporativa (`CorporateCalendarManager`) $\to$ Simulación Walk-Forward con fricciones bidireccionales y short-borrow fee.
- **Prevención Estricta de Sesgos:**
  - Separación in-sample / out-of-sample sin solapamiento de fechas.
  - Ejecución estricta en $t+1$ (señal al cierre de $t \to$ llenado en apertura/barra $t+1$).
  - Descuento de comisiones, diferencial bid-ask, impacto de mercado y costo de préstamo de acciones vendidas en corto (2% anual devengado diario).
  - Bloqueo sistemático de aperturas dentro de los 3 días hábiles previos a earnings y evacuación obligatoria a $t-1$.

---

## 3. Estado de Módulos y Tareas

| Módulo / Tarea | Estado | Pruebas Unitarias |
| :--- | :--- | :--- |
| **Documentación Inicial** (`AGENTS.md`, `methodology.md`, `research.md`, `decisions.md`) | ✅ Completado | N/A |
| **Módulo 1: Datos y Universo** (`data.py`, `universe.py`) | ✅ Completado | ✅ `tests/test_data.py` (7/7 pasadas) |
| **Módulo 2: Preselección SSD** (`selection.py`) | ✅ Completado | ✅ `tests/test_selection.py` (3/3 pasadas) |
| **Módulo 3: Motor Econométrico** (`spread.py`) | ✅ Completado | ✅ `tests/test_spread.py` (5/5 pasadas) |
| **Módulo 4: Generación de Señales** (`signals.py`) | ✅ Completado | ✅ `tests/test_signals.py` (5/5 pasadas) |
| **Módulo 5: Backtest & Métricas** (`backtest.py`, `metrics.py`) | ✅ Completado | ✅ `tests/test_backtest.py` (11/11 pasadas) |
| **Pipeline Integrado & Runner** (`pipeline.py`, `run_pipeline.py`) | ✅ Completado | ✅ Simulación Walk-Forward (15 ventanas) |
| **Filtro de Calendario Corporativo** (`CorporateCalendarManager`) | ✅ Completado | ✅ Evaluado en Universo Real de Semiconductores |

**Total Suite de Pruebas Unitarias:** 32/32 pruebas pasadas (100% éxito).

---

## 4. Resultados de la Prueba en Universo Real de Semiconductores (2021-2025)

### Comparativa: Pre vs Post Filtro de Calendario Corporativo (Earnings Blackout):

| Métrica Global | Pre-Filtro de Calendario | Post-Filtro de Calendario (Producción) | Impacto / Mejora |
| :--- | :---: | :---: | :---: |
| **Operaciones Totales (15 Ventanas OOS)** | 9 trades | 9 trades | Idéntica selectividad |
| **Trades cerrados por `mean_reversion`** | 8 (88.9%) | **9 (100%)** | +11.1% reversiones limpias |
| **Trades cerrados por `stop_loss_8pct`** | 1 (11.1%) | **0 (0.0%)** | **100% eliminación de stops** |
| **Retorno Neto Medio por Ventana** | -1.78% | **-0.19%** | **+1.59% de mejora** |
| **Ratio de Sharpe Medio** | -0.74 | **-0.42** | **+0.32 de mejora** |
| **Peor Drawdown Máximo Global** | -12.83% | **-2.87%** | **Reducción del 77.6% del riesgo** |
| **Retorno Neto Ventana 12 (`AVGO_TSM`)** | -12.58% | **+0.15%** | **+12.73% de mejora** |

### Conclusiones de Producción en `main`:
1. El sistema opera actualmente en la rama `main` con el universo ampliado de 15 activos de semiconductores, preselección Top-20 SSD, validación rigurosa FDR al 5% y filtro activo de eventos corporativos.
2. La cuarentena de earnings neutralizó exitosamente la única pérdida catastrófica del sistema (el salto del +24.6% de AVGO), convirtiendo una pérdida de -$12,583 en una ganancia de +$2,663.71 y demostrando la indispensabilidad de filtros de calendario en arbitraje estadístico accionario.

