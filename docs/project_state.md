# Estado del Proyecto: Arbitraje Estadístico de Pares

* **Fecha de actualización:** 2026-10-27
* **Fase Actual:** Fase 6 Completada — Sistema Integral Modular y Simulación Walk-Forward Validada

---

## 1. Objetivos del Proyecto
Desarrollar un sistema modular, reproducible y riguroso para investigar estrategias de arbitraje estadístico y reversión a la media en acciones, verificando fuera de muestra y tras costos si existe una ventaja cuantitativa explotable sin optimización prematura.

---

## 2. Decisiones y Hechos Verificados
- **Stack Tecnológico:** Python 3.11 (`pandas`, `numpy`, `scipy`, `statsmodels`, `pytest`).
- **Arquitectura Funnel:** Preselección rápida por distancia SSD $\to$ Validación econométrica rigurosa (Engle-Granger, Johansen, OU, FDR Benjamini-Hochberg) $\to$ Filtro de Kalman secuencial para hedge ratio $\beta_t \to$ Señales elásticas GARCH con fallback $\to$ Simulación Walk-Forward con fricciones bidireccionales y short-borrow fee.
- **Prevención Estricta de Sesgos:**
  - Separación in-sample / out-of-sample sin solapamiento de fechas.
  - Ejecución estricta en $t+1$ (señal al cierre de $t \to$ llenado en apertura/barra $t+1$).
  - Descuento de comisiones, diferencial bid-ask, impacto de mercado y costo de préstamo de acciones vendidas en corto (2% anual devengado diario).

---

## 3. Estado de Módulos y Tareas

| Módulo / Tarea | Estado | Pruebas Unitarias |
| :--- | :--- | :--- |
| **Documentación Inicial** (`AGENTS.md`, `methodology.md`, `research.md`, `decisions.md`) | ✅ Completado | N/A |
| **Módulo 1: Datos y Universo** (`data.py`, `universe.py`) | ✅ Completado | ✅ `tests/test_data.py` (7/7 pasadas) |
| **Módulo 2: Preselección SSD** (`selection.py`) | ✅ Completado | ✅ `tests/test_selection.py` (3/3 pasadas) |
| **Módulo 3: Motor Econométrico** (`spread.py`) | ✅ Completado | ✅ `tests/test_spread.py` (5/5 pasadas) |
| **Módulo 4: Generación de Señales** (`signals.py`) | ✅ Completado | ✅ `tests/test_signals.py` (5/5 pasadas) |
| **Módulo 5: Backtest & Métricas** (`backtest.py`, `metrics.py`) | ✅ Completado | ✅ `tests/test_backtest.py` (5/5 pasadas) |
| **Pipeline Integrado & Runner** (`pipeline.py`, `run_pipeline.py`) | ✅ Completado | ✅ Simulación Walk-Forward (5 ventanas) |

**Total Suite de Pruebas Unitarias:** 25/25 pruebas pasadas (100% éxito).

---

## 4. Resultados de la Simulación Walk-Forward
Ejecutada sobre 5 ventanas móviles (252 barras formación / 63 barras negociación fuera de muestra):
- Reducción combinatoria de 45 pares a Top-10 candidatos por SSD.
- Filtrado econométrico efectivo: solo 1 a 2 pares superan simultáneamente Cointegración, Half-Life viable y control de FDR Benjamini-Hochberg.
- Resultados fuera de muestra realistas: alternancia de ventanas con rendimiento positivo y ventanas con drawdowns/stops, evidenciando el impacto de la fricción y la no estacionariedad sin sobreajuste.
- Reportes consolidados exportados a `results/walk_forward_summary.csv` y `results/walk_forward_raw.json`.
