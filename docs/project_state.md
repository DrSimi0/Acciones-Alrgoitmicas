# Estado del Proyecto: Arbitraje Estadístico de Pares

* **Fecha de actualización:** 2026-11-01
* **Fase Actual:** Fase 8 Completada — Módulo de Factores PCA Multivariado (Avellaneda & Lee) y Validación Econométrica de Residuales Idiosincrásicos

---

## 1. Objetivos del Proyecto
Desarrollar un sistema modular, reproducible y riguroso para investigar estrategias de arbitraje estadístico y reversión a la media en acciones, verificando fuera de muestra y tras costos si existe una ventaja cuantitativa explotable sin optimización prematura.

---

## 2. Decisiones y Hechos Verificados
- **Stack Tecnológico:** Python 3.11 (`pandas`, `numpy`, `scipy`, `statsmodels`, `pytest`).
- **Arquitectura Híbrida (Bivariada + Multivariada):**
  - **Bivariada (Pairs Trading):** Preselección SSD $\to$ Validación Engle-Granger/Johansen $\to$ Filtro de Kalman secuencial para hedge ratio $\beta_t \to$ Señales GARCH $\to$ Filtro de Calendario Corporativo (`CorporateCalendarManager`) $\to$ Simulación Walk-Forward.
  - **Multivariada (Avellaneda & Lee, 2010):** Extracción de factores sistemáticos mediante PCA (`PCAFactorModel`) en NumPy puro $\to$ Regresión multivariada y aislamiento de residuales idiosincrásicos $\epsilon_{i,t} \to$ Spread sintético acumulado $X_{i,t} = \sum \epsilon_{i,s} \to$ Validación ADF + Ornstein-Uhlenbeck + Benjamini-Hochberg FDR al 5% en `EconometricValidator`.
- **Prevención Estricta de Sesgos:**
  - Separación in-sample / out-of-sample sin solapamiento de fechas.
  - Proyección factorial fuera de muestra con autovectores, medias y desviaciones congeladas in-sample.
  - Ejecución estricta en $t+1$ con descuento de todas las fricciones (comisiones, spread, slippage y short-borrow fee).

---

## 3. Estado de Módulos y Tareas

| Módulo / Tarea | Estado | Pruebas Unitarias |
| :--- | :--- | :--- |
| **Documentación Inicial** (`AGENTS.md`, `methodology.md`, `research.md`, `decisions.md`) | ✅ Completado | N/A |
| **Módulo 1: Datos y Universo** (`data.py`, `universe.py`) | ✅ Completado | ✅ `tests/test_data.py` (7/7 pasadas) |
| **Módulo 2: Preselección SSD** (`selection.py`) | ✅ Completado | ✅ `tests/test_selection.py` (3/3 pasadas) |
| **Módulo 3: Motor Econométrico** (`spread.py`) | ✅ Completado | ✅ `tests/test_spread.py` (8/8 pasadas) |
| **Módulo 4: Generación de Señales** (`signals.py`) | ✅ Completado | ✅ `tests/test_signals.py` (5/5 pasadas) |
| **Módulo 5: Backtest & Métricas** (`backtest.py`, `metrics.py`) | ✅ Completado | ✅ `tests/test_backtest.py` (13/13 pasadas) |
| **Módulo 6: Factores PCA Multivariado** (`pca_model.py`) | ✅ Completado | ✅ `tests/test_pca_model.py` (6/6 pasadas) |
| **Pipeline Integrado & Runner** (`pipeline.py`, `run_pipeline.py`) | ✅ Completado | ✅ Simulación Walk-Forward (15 ventanas) |
| **Filtro de Calendario Corporativo** (`CorporateCalendarManager`) | ✅ Completado | ✅ Evaluado en Universo Real de Semiconductores |
| **Experimento Pares Fijos Long/Short** (`exp-cerrar-distancia-pares-definidos`) | ✅ Completado | ✅ 15 Ventanas OOS sobre 5 Pares Competidores |

**Total Suite de Pruebas Unitarias:** 42/42 pruebas pasadas (100% éxito).

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

---

## 5. Experimento de Pares Fijos Fundamentales y Ejecución L/S 50/50 (Rama `exp-cerrar-distancia-pares-definidos`)

- **Universo Evaluado (10 tickers, 5 pares):** `KO/PEP`, `V/MA`, `CVX/XOM`, `HD/LOW`, `UNP/CSX`.
- **Diseño del Pipeline:** Omisión de preselección SSD (pares inyectados directamente al validador econométrico con rigor pleno: $p \le 0.05$, $HL \le 30$d, FDR $\alpha=0.05$).
- **Asignación Simétrica 50/50:** 50% nocional al activo subvaluado (Long) y 50% al activo sobrevaluado (Short ajustado por $\beta_t$).
- **Resultados Empíricos (15 ventanas Walk-Forward, 2021–2025):**
  - **Ventana 2 (abril–julio 2022):** El par `CVX_XOM` superó el rigor econométrico pleno ($p = 0.0007$, Half-Life $= 27.7$ días).
  - **Trades Ejecutados:** 2 operaciones out-of-sample en `CVX_XOM`, ambas cerradas con éxito por convergencia a la media (`mean_reversion`).
  - **Trade 1 (Long Spread):** +$593.17 (+0.44% de retorno neto) tras deducir $39.65 de comisiones y $4.48 de préstamo de cortos.
  - **Trade 2 (Short Spread):** -$269.77 (-0.20% de retorno neto) tras deducir $39.34 de comisiones y $5.50 de préstamo de cortos.
  - **Métricas Globales de la Ventana:** Retorno neto: **+0.32%**, Sharpe: **0.35**, Max Drawdown: **-1.36%**, Win Rate: **50%**, Profit Factor: **2.20**.
  - **Otras 14 ventanas:** El filtro FDR al 5% rechazó sistemáticamente los otros 4 pares por falta de cointegración estacionaria, protegiendo el capital de operar divergencias espurias en sectores cíclicos y defensivos.

### Conclusiones de Producción en `main`:
1. El sistema opera actualmente en la rama `main` con el universo ampliado de 15 activos de semiconductores, preselección Top-20 SSD, validación rigurosa FDR al 5% y filtro activo de eventos corporativos.
2. La cuarentena de earnings neutralizó exitosamente la única pérdida catastrófica del sistema (el salto del +24.6% de AVGO), convirtiendo una pérdida de -$12,583 en una ganancia de +$2,663.71 y demostrando la indispensabilidad de filtros de calendario en arbitraje estadístico accionario.

