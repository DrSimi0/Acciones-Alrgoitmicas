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
| **Prueba en Universo Real (7 Activos)** (`run_pipeline.py`, `yfinance`) | ✅ Completado | ✅ 15 Ventanas Walk-Forward (2021-2025) |

**Total Suite de Pruebas Unitarias:** 28/28 pruebas pasadas (100% éxito).

---

## 4. Resultados de la Prueba en Universo Real (2021-2025)
Ejecutada con `yfinance` sobre `["NVDA", "AAPL", "SBUX", "JPM", "JNJ", "XOM", "SPY"]`:
- **Ventanas procesadas:** 15 ventanas Walk-Forward (252 barras In-Sample / 63 barras Out-of-Sample).
- **Filtro SSD:** Preseleccionó entre 3 y 10 candidatos por ventana con correlaciones altas ($r > 0.85$).
- **Filtro Econométrico Riguroso (Engle-Granger + Johansen + FDR):** **Rechazó el 100% de los pares** en todas las 15 ventanas ($p > 0.05$).
- **Conclusión Empírica Clave:** La alta correlación no implica cointegración. Entre 2021 y 2025, la divergencia secular de múltiplos (ej. rally de IA en NVDA frente al sector defensivo o financiero) generó spreads no estacionarios $I(1)$. El motor protegió el capital al **no forzar operaciones espurias sin reversión a la media garantizada**.
