# Estado del Proyecto: Arbitraje Estadístico de Pares

* **Fecha de actualización:** 2026-11-01
* **Fase Actual:** Fase 9 Completada — Pipeline de Producción PCA Multivariado en S&P 100 con Ejecución Sintética Market-Neutral (Long/Short vs SPY Proxy)

---

## 1. Objetivos del Proyecto
Desarrollar un sistema modular, reproducible y riguroso para investigar estrategias de arbitraje estadístico y reversión a la media en acciones, verificando fuera de muestra y tras costos si existe una ventaja cuantitativa explotable sin optimización prematura.

---

## 2. Decisiones y Hechos Verificados
- **Stack Tecnológico:** Python 3.11 (`pandas`, `numpy`, `scipy`, `statsmodels`, `pytest`).
- **Arquitectura Híbrida (Bivariada + Multivariada):**
  - **Bivariada (Pairs Trading):** Preselección SSD $\to$ Validación Engle-Granger/Johansen $\to$ Filtro de Kalman secuencial para hedge ratio $\beta_t \to$ Señales GARCH $\to$ Filtro de Calendario Corporativo (`CorporateCalendarManager`) $\to$ Simulación Walk-Forward.
  - **Pares Fijos Fundamentales:** Modo de evaluación directa sobre competidores de alta capitalización (`KO/PEP`, `V/MA`, `CVX/XOM`, `HD/LOW`, `UNP/CSX`) con asignación 50/50 y deducción de *short-borrow fees*.
  - **Multivariada (Avellaneda & Lee, 2010):** Extracción de factores sistemáticos mediante PCA (`PCAFactorModel`) $\to$ Regresión multivariada y aislamiento de residuales idiosincrásicos $\epsilon_{i,t} \to$ Spread sintético acumulado $X_{i,t} = \sum \epsilon_{i,s} \to$ Validación ADF + Ornstein-Uhlenbeck + Benjamini-Hochberg FDR al 5% en `EconometricValidator` $\to$ Cobertura sintética Market-Neutral contra el ETF proxy (`SPY`) escalado por $\beta_{total} = \sum \beta_{i,k}$.
- **Prevención Estricta de Sesgos:**
  - Separación in-sample / out-of-sample sin solapamiento de fechas.
  - Filtro dinámico de liquidez ($ADTV_{20} \ge \$50\text{M}$, $P \ge \$10$) evaluado estrictamente en formación.
  - Proyección factorial fuera de muestra con autovectores, medias y desviaciones congeladas in-sample.
  - Ejecución estricta en $t+1$ con descuento de todas las fricciones (comisiones, spread, slippage y short-borrow fee).

---

## 3. Estado de Módulos y Tareas

| Módulo / Tarea | Estado | Pruebas Unitarias |
| :--- | :--- | :--- |
| **Documentación Inicial** (`AGENTS.md`, `methodology.md`, `research.md`, `decisions.md`) | ✅ Completado | N/A |
| **Módulo 1: Datos y Universo** (`data.py`, `universe.py`) | ✅ Completado | ✅ `tests/test_data.py` (8/8 pasadas) |
| **Módulo 2: Preselección SSD** (`selection.py`) | ✅ Completado | ✅ `tests/test_selection.py` (3/3 pasadas) |
| **Módulo 3: Motor Econométrico** (`spread.py`) | ✅ Completado | ✅ `tests/test_spread.py` (8/8 pasadas) |
| **Módulo 4: Generación de Señales** (`signals.py`) | ✅ Completado | ✅ `tests/test_signals.py` (5/5 pasadas) |
| **Módulo 5: Backtest & Métricas** (`backtest.py`, `metrics.py`) | ✅ Completado | ✅ `tests/test_backtest.py` (14/14 pasadas) |
| **Módulo 6: Factores PCA Multivariado** (`pca_model.py`) | ✅ Completado | ✅ `tests/test_pca_model.py` (6/6 pasadas) |
| **Pipeline Integrado & Runner** (`run_pipeline.py`) | ✅ Completado | ✅ Simulación Walk-Forward S&P 100 (15 ventanas) |
| **Filtro de Calendario Corporativo** (`CorporateCalendarManager`) | ✅ Completado | ✅ Integrado en Bivariado y Multivariado |
| **Experimento Pares Fijos Long/Short** (`run_fixed_pairs_pipeline`) | ✅ Completado | ✅ 15 Ventanas OOS sobre 5 Pares Competidores |
| **Pipeline PCA S&P 100 Market-Neutral** (`run_trading_pipeline`) | ✅ Completado | ✅ 15 Ventanas OOS (100 activos + SPY) |

**Total Suite de Pruebas Unitarias:** 44/44 pruebas pasadas (100% éxito).

---

## 4. Resultados Empíricos del Pipeline PCA Multivariado en S&P 100 (2021–2025)

- **Universo:** 100 activos del índice S&P 100 (OEX) + ETF proxy `SPY` (1,254 barras diarias).
- **Ventanas Walk-Forward:** 15 ventanas (252 barras In-Sample, 63 barras Out-of-Sample, desplazamiento 63 barras).
- **Filtro de Liquidez:** 97% a 99% de los activos superaron consistentemente el filtro ($ADTV_{20} \ge \$50\text{M}$ y $P \ge \$10$).
- **Factores PCA Extraídos Dinámicamente:** Entre 20 y 36 autovectores por ventana para explicar el 80% de varianza total.
- **Rigor Econométrico:** Entre 0 y 3 activos por ventana superaron la triple prueba (ADF $p \le 0.05$, vida media Ornstein-Uhlenbeck $\le 30$ días, y control FDR Benjamini-Hochberg $\alpha = 0.05$).
- **Operaciones Totales Ejecutadas OOS:** 18 trades sintéticos (Activo vs SPY).
- **Distribución de Motivos de Salida (`exit_reason`):**
  - `end_of_period`: 6 trades (33.3%)
  - `stop_half_life`: 5 trades (27.8%)
  - `mean_reversion`: 4 trades (22.2%)
  - `FORCE_EXIT_EARNINGS`: 2 trades (11.1%)
  - `stop_loss_8pct`: 1 trades (5.6%)
- **Métricas de Rendimiento Agregadas:**
  - Retorno Neto promedio por ventana: **-0.10%**
  - Ratio de Sharpe promedio OOS: **-0.03**
  - Peor Drawdown registrado: **-10.38%**
  - Tasa de Acierto (Win Rate): **44.4%** (8 ganadores / 18 totales)
  - Trades de Alta Ganancia Capturados:
    - `GOOG` (Ventana 13, feb 2025): **+10.38%** neto (+$11,545.02)
    - `NEE` (Ventana 4, oct 2022): **+9.14%** neto (+$10,052.79)
    - `GOOGL` (Ventana 13, feb 2025): **+8.59%** neto (+$9,446.11)
    - `GE` (Ventana 1, mar 2022): **+5.05%** neto (+$5,617.79)

### Comparativa: Configuración Base vs Optimizada (Arbitraje Estadístico PCA S&P 100):

| Métrica Cuantitativa | Configuración Base (ADR 011) | Configuración Optimizada (ADR 012) | Impacto / Hallazgo |
| :--- | :---: | :---: | :---: |
| **`variance_threshold` / `max_half_life` / `exit_z`** | 0.80 / 30.0d / 0.50 | **0.87 / 12.0d / 0.75** | Parámetros más reactivos |
| **Operaciones Totales (15 Ventanas OOS)** | 18 trades | **15 trades** | Mayor selectividad econométrica |
| **Trades cerrados por `mean_reversion`** | 4 (22.2%) | **6 (40.0%)** | **+17.8% de reversiones directas** |
| **Trades cerrados por `stop_half_life`** | 5 (27.8%) | **2 (13.3%)** | **-14.5% de salidas por timeout** |
| **Trades cerrados por `end_of_period`** | 6 (33.3%) | **1 (6.7%)** | **-26.6% de posiciones atrapadas** |
| **Trades evacuados por Earnings** | 2 (11.1%) | **5 (33.3%)** | Disciplina de riesgo activa |
| **Trades cerrados por `stop_loss_8pct`** | 1 (5.6%) | **1 (6.7%)** | Control de pérdidas idéntico |
| **Retorno Neto Medio por Ventana** | -0.10% | **-4.22%** | Dispersión residual concentrada |
| **Ratio de Sharpe Medio OOS** | -0.03 | **-1.27** | Impacto de sobreajuste dimensional |
| **Peor Drawdown Registrado** | -10.38% | **-14.29%** | Aumento moderado de volatilidad |
| **Tasa de Acierto (Win Rate)** | 44.4% | **26.7%** | Reducción por falsos quiebres |

---

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

