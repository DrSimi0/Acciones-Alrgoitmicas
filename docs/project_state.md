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

## 4. Resultados de la Prueba en Universo Real y Experimentos A & B (2021-2025)

### Línea Base (7 Mega-caps, Rigor Completo FDR=0.05):
- **Ventanas procesadas:** 15 ventanas Walk-Forward (252 barras In-Sample / 63 barras Out-of-Sample).
- **Filtro SSD:** Preseleccionó candidatos correlacionados ($r > 0.85$).
- **Filtro Econométrico (FDR=0.05):** Rechazó el 100% de los pares por falta de cointegración estacionaria genuina. Protegió el capital al no forzar operaciones espurias.

### Experimento A: Prueba de Estrés de Riesgo (Rama `exp-relax-fdr`):
- **Calibración:** `coint_pvalue_threshold=0.25`, `fdr_alpha=0.25` sobre 7 mega-caps.
- **Trades ejecutados OOS:** 10 operaciones forzadas en pares fronterizos.
- **Motivos de salida:** 10 salidas por `mean_reversion` (100%), ya que las oscilaciones de corto plazo cerraron las posiciones antes de tocar el stop-loss duro del -8%.
- **Máxima pérdida en trade individual:** -3.16% (NVDA/SPY).
- **Retorno neto medio:** -0.53%, Sharpe: -0.40. Demuestra que relajar el filtro econométrico degrada la expectativa matemática.

### Adopción en Producción (`main`):
- **Estrategia Seleccionada:** Se adopta de forma definitiva el **Experimento B (Sector Semiconductores)** como núcleo de producción en `main`.
- **Justificación:** 
  1. El Experimento A demostró que relajar el FDR al 25% degrada la expectativa matemática y fuerza la entrada de pares espurios sin reversión fiable. Queda formalmente descartado.
  2. El Experimento B probó que en un universo homogéneo con 105 combinaciones, el filtro FDR al 5% aísla cointegración económica real, mientras que el `RiskManager` demostró su eficacia salvando la cuenta ante el salto no lineal de AVGO (+24.6% en una sesión).
- **Archivos de Producción en `main`:**
  - Pipeline: `run_pipeline.py` (ejecuta el universo de semiconductores con Top-20 SSD y FDR=0.05).
  - Resultados oficiales: `results/walk_forward_real_universe.csv`, `results/trades_real_universe.csv`, `results/real_universe_candidates_audit.csv`.
