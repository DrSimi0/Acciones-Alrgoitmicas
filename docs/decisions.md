# Registro de Decisiones de Arquitectura (ADRs)

Este documento registra las decisiones técnicas clave, su contexto y sus justificaciones.

---

## ADR 001: Arquitectura de Embudo (Funnel) de Dos Pasos
* **Fecha:** 2026-10-27
* **Estado:** Aceptado
* **Contexto:** En un universo de $N$ acciones, existen $\mathcal{O}(N^2)$ pares potenciales. Probar cointegración y Ornstein-Uhlenbeck para todas las combinaciones es prohibitivamente costoso computacionalmente e infla la tasa de falsos descubrimientos.
* **Decisión:** Implementar un embudo:
  1. Filtro rápido de distancia euclidiana SSD en `selection.py` para aislar el Top-K de pares.
  2. Validación econométrica rigurosa (Engle-Granger, Johansen, OU Half-Life y FDR) en `spread.py` sobre los pares preseleccionados.
* **Consecuencias:** Máxima eficiencia computacional con rigor estadístico preservado.

---

## ADR 002: Normalización por Log-Precios Estandarizados en SSD
* **Fecha:** 2026-10-27
* **Estado:** Aceptado
* **Contexto:** Normalizar con $P_t / P_0$ genera sesgo dependiente de anomalías en $t=0$.
* **Decisión:** Estandarizar la serie de log-precios longitudinalmente en la ventana de formación.
* **Consecuencias:** Mayor robustez del comovimiento sin distorsión por la cotización inicial.

---

## ADR 003: Inclusión de Costos de Préstamo de Cortos (*Short-Borrow Fee*)
* **Fecha:** 2026-10-27
* **Estado:** Aceptado
* **Contexto:** El pairs trading requiere vender en corto una acción; obviar el costo de préstamo infla artificialmente el Sharpe y el retorno neto.
* **Decisión:** Incorporar el parámetro `short_borrow_rate_annual` (devengado diariamente) en el motor de backtesting.
* **Consecuencias:** Simulaciones out-of-sample financieramente realistas.

---

## ADR 004: Fallback Robusto en Estimación GARCH(1,1)
* **Fecha:** 2026-10-27
* **Estado:** Aceptado
* **Contexto:** La optimización de máxima verosimilitud en GARCH(1,1) puede no converger en ventanas de mercado con cambios abruptos de régimen.
* **Decisión:** Implementar fallback automático a volatilidad EWMA / rolling std ante `ConvergenceWarning` o fallo de optimización.
* **Consecuencias:** Estabilidad absoluta del pipeline de señales sin interrupciones.

---

## ADR 005: Control de Riesgos Dual (Kalman Breakdown + Hard Stop-Loss por Capital)
* **Fecha:** 2026-10-28
* **Estado:** Aceptado
* **Contexto:** La cointegración in-sample puede fracturarse violentamente fuera de muestra debido a divergencias seculares o anuncios de resultados no anticipados.
* **Decisión:** Implementar dos capas de defensa en numpy puro:
  1. `KalmanSpreadTracker`: Monitoreo del elemento $P_{1,1}$ (incertidumbre de $\beta_t$). Si supera un umbral crítico, emite `is_broken = True` cerrando la posición por `stop_kalman_breakdown`.
  2. `RiskManager`: Monitoreo del PnL no realizado sobre el valor nocional absoluto comprometido ($|shares_A \cdot P_A| + |shares_B \cdot P_B|$). Si la pérdida flotante alcanza el límite máximo (-8%), fuerza una liquidación inmediata `stop_loss_8pct` y activa un cooldown para evitar re-entradas suicidas en la misma divergencia.
* **Consecuencias:** Amputación garantizada de colas izquierdas catastróficas.

---

## ADR 006: Taxonomía de Motivos de Salida (`exit_reason`) y Contabilidad de Caja Pura
* **Fecha:** 2026-10-30
* **Estado:** Aceptado
* **Contexto:** La auditoría empírica de operaciones requiere distinguir claramente si un trade cerró por convergencia estadística (`mean_reversion`), tiempo (`stop_half_life`), quiebre estructural (`stop_structural_break`), incertidumbre (`stop_kalman_breakdown`) o límite de capital (`stop_loss_8pct`).
* **Decisión:** 
  1. Registrar `exit_reason` individual en cada orden cerrada y exportar `results/trades_*.csv`.
  2. Corregir y auditar la contabilidad de caja en `simulate_pair`: flujo de caja unificado $Cash \leftarrow Cash - \Delta S \cdot P_{exec} - Comm$ y cálculo de PnL exacto por patas sin distorsiones por rebalanceos intermedios.
* **Consecuencias:** Trazabilidad absoluta de cada dólar ganado o perdido por el sistema.

---

## ADR 007: Adopción del Universo Sectorial de Semiconductores como Núcleo de Producción
* **Fecha:** 2026-10-30
* **Estado:** Aceptado
* **Contexto:** 
  1. El universo heterogéneo de 7 mega-caps generó 0 trades con FDR=0.05 y resultados destructivos (-0.53%, Sharpe -0.40) cuando se relajó el FDR al 25% (Experimento A).
  2. El universo sectorial de 15 activos de semiconductores (105 combinaciones) comparte factores sistemáticos y cadenas de suministro estrechamente ligadas.
* **Decisión:**
  1. Adoptar oficialmente la configuración del **Experimento B** en la rama `main`: 15 semiconductores, preselección SSD Top-20, rigor pleno de cointegración ($p \le 0.05$, $HL \le 30\text{d}$, $\text{FDR} \le 0.05$) y Hard Stop-Loss (-8%).
  2. Descartar el enfoque de relajación de FDR (Experimento A) por inducir sobreoperación en series no estacionarias.
* **Consecuencias:** Se establece una base reproducible con cointegración genuina y mitigación activa de colas izquierdas demostrada en mercado real.

---

## ADR 008: Filtro de Cuarentena y Evacuación por Calendario Corporativo (Earnings Blackout Filter)
* **Fecha:** 2026-10-30
* **Estado:** Aceptado
* **Contexto:** Los anuncios de resultados trimestrales (*earnings announcements*) representan eventos discretos de información asimétrica capaces de inducir brechas nocturnas (*overnight gaps*) y saltos de volatilidad no continuos que rompen de forma exógena la relación de cobertura $\beta_t$.
* **Decisión:** Implementar la clase `CorporateCalendarManager` integrada en `WalkForwardBacktester`:
  1. **Cuarentena Previa (`is_in_quarantine`):** Bloquear aperturas de nuevas posiciones si alguno de los activos reporta resultados en los próximos 3 días hábiles.
  2. **Evacuación Preventiva (`requires_evacuation`):** Liquidar forzadamente a mercado posiciones abiertas si cualquiera de los activos reporta al día hábil siguiente (`FORCE_EXIT_EARNINGS`).
  3. **Operación en Paralelo:** Coexistencia con el *Hard Stop-Loss* (-8%) y el filtro Kalman de incertidumbre.
* **Consecuencias:** Eliminación sistemática del riesgo idiosincrásico por gaps de earnings.

---

## ADR 009: Descomposición Multivariada por Factores Estadísticos PCA (Avellaneda & Lee, 2010)
* **Fecha:** 2026-11-01
* **Estado:** Aceptado
* **Contexto:** El enfoque bivariado ($A$ vs $B$) evalúa pares aislados, omitiendo que las correlaciones entre acciones se derivan de factores de riesgo sistemáticos compartidos (mercado general y subsectores). En universos densos, modelar pares individuales genera redundancia y susceptibilidad a falsos descubrimientos.
* **Decisión:**
  1. Implementar la clase `PCAFactorModel` en `src/pca_model.py` basada en Avellaneda & Lee (2010), descomponiendo la matriz de correlación empírica en autovectores y autovalores ortonormales en NumPy puro.
  2. Seleccionar dinámicamente $K$ factores principales para capturar el umbral de riesgo sistemático (`variance_threshold = 0.80`).
  3. Regresar cada activo contra los $K$ factores mediante OLS simultáneo para extraer la serie de retornos idiosincrásicos $\epsilon_{i,t}$ y el spread sintético acumulado $X_{i,t} = \sum_{s=1}^t \epsilon_{i,s}$.
  4. Extender `EconometricValidator` en `src/spread.py` con `test_residual_stationarity` (ADF) y `validate_pca_residuals` (ADF + Ornstein-Uhlenbeck + Benjamini-Hochberg FDR al 5%) para validar rigurosamente la reversión de cada residual individual sin minería de datos.
* **Consecuencias:** Se establece el núcleo matemático para evolucionar de pairs trading a carteras sintéticas neutrales a mercado y a factores.

---

## ADR 010: Ejecución Simétrica Market-Neutral (Long/Short 50/50) y Pares Fijos Fundamentales
* **Fecha:** 2026-11-01
* **Estado:** Aceptado
* **Contexto:**
  1. En la asignación original proporcional a $1 / (1 + \beta)$, activos con $\beta > 1$ inducían una asimetría nocional que reducía la neutralidad en dólares del portafolio.
  2. Evaluar universos masivos mediante preselección por distancia SSD puede omitir pares con lógica económica y competitiva directa evidente (ej. Coca-Cola vs Pepsi, Visa vs Mastercard, Chevron vs ExxonMobil).
* **Decisión:**
  1. Implementar `capital_allocation_mode="symmetric_50_50"` en `WalkForwardBacktester`: asignación exacta del 50% del capital al activo subvaluado (Long) y 50% al activo sobrevaluado (Short con ajuste de cobertura beta $\beta_t$).
  2. Deducir formalmente el costo de préstamo de cortos (*short-borrow fee*) acumulado durante el ciclo de vida del trade directamente en su PnL neto individual y registrar el desglose por patas (`pnl_leg_a` y `pnl_leg_b`).
  3. Crear `run_fixed_pairs_pipeline()` en `run_pipeline.py` para evaluar pares de competidores directos omitiendo el filtro SSD, inyectándolos de forma directa al validador econométrico con control FDR al 5% y al filtro de calendario corporativo.
* **Consecuencias:** Neutralidad nocional robusta, contabilidad de caja y préstamo de cortos exacta por trade, y capacidad de contrastar hipótesis fundamentales directas sin dependencia de minería de distancia.

---

## ADR 011: Pipeline de Producción PCA Multivariado en S&P 100 con Cobertura Sintética Market-Neutral (SPY Proxy)
* **Fecha:** 2026-11-01
* **Estado:** Aceptado
* **Contexto:**
  1. Escalar el sistema de arbitraje estadístico de pares bivariados a carteras de acciones de alta liquidez requiere desacoplar el riesgo idiosincrásico individual del riesgo de mercado general.
  2. En el marco de Avellaneda & Lee (2010), cada acción individual que exhibe una desviación temporal en su residual estocástico $X_{i,t}$ se negocia no contra otra acción única, sino contra el mercado o factor sectorial proxy (ej. ETF `SPY`) escalado por su sensibilidad sistemática global ($\beta_{total} = \sum_{k=1}^K \beta_{i,k}$).
* **Decisión:**
  1. **Universo Amplio de Producción:** Adoptar los 100 activos del índice S&P 100 (OEX) más el ETF proxy `SPY` (101 activos en total) para el periodo 2021-2025 (1,254 barras sincronizadas).
  2. **Filtro Dinámico de Liquidez In-Sample:** Descartar en cada ventana Walk-Forward activos con $\text{ADTV}_{20} < \$50\text{M}$ o precio $< \$10$ evaluados exclusivamente en las últimas 20 barras del periodo de formación (cero look-ahead bias).
  3. **Extracción y Validación Econométrica:** Ajustar `PCAFactorModel(variance_threshold=0.80)` sobre los retornos in-sample de los activos líquidos. Validar los spreads sintéticos acumulados $X_{i,t}$ con `EconometricValidator.validate_pca_residuals` (ADF $p \le 0.05$, vida media OU $\le 30$ días, y control FDR Benjamini-Hochberg al 5%).
  4. **Ejecución Long/Short Sintética (`synthetic_pca`):** Asignar 100% del capital de la orden a la acción individual (Pata Larga si subvaluada, Pata Corta si sobrevaluada) y tomar la posición contraria en el ETF proxy `SPY` escalada por $\beta_{total}$. Deducir daily borrow fees sobre la pata corta y registrar métricas independientes por pata (`pnl_leg_asset`, `pnl_leg_proxy`, `borrow_fees`, `commissions`).
  5. **Orquestación Central:** Establecer `run_trading_pipeline()` como el flujo por defecto de `run_pipeline.py`.
* **Consecuencias:** Cobertura market-neutral estricta frente a factores macroeconómicos, diversificación transversal a través del S&P 100 y mitigación matemática de minería de datos mediante FDR.

---

## ADR 012: Optimización de Hiperparámetros de Rotación y Pureza en el Pipeline PCA
* **Fecha:** 2026-11-01
* **Estado:** Aceptado
* **Contexto:** En la configuración base del pipeline PCA S&P 100 (ADR 011), el 33.3% de las operaciones cerraban por vencimiento de ventana trimestral (`end_of_period`) y el 27.8% por timeout de vida media (`stop_half_life`), denotando una permanencia excesiva que acumulaba fricciones y comisiones de préstamo de cortos (*short-borrow fees*).
* **Decisión:**
  1. **Pureza Residual:** Elevar `variance_threshold` de `0.80` a `0.87` en `PCAFactorModel` para aislar un ruido idiosincrásico más reactivo frente a factores macro.
  2. **Velocidad de Reversión:** Reducir `max_half_life` de `30.0` a `12.0` días en `EconometricValidator`, descartando de forma estricta series con tendencia al letargo.
  3. **Toma de Ganancias Anticipada:** Ajustar `exit_z` de `0.50` a `0.75` en `SignalGenerator` para capturar la parte vertical de la reversión a la media.
  4. **Exportación Segregada:** Guardar resultados en `results/*_optimized.csv` y `.json`.
* **Consecuencias:** Se eliminaron casi por completo las posiciones atrapadas al cierre del trimestre (reducción de `end_of_period` del 33.3% al 6.7%) y los timeouts de vida media cayeron del 27.8% al 13.3%, elevando la tasa de salidas limpias por reversión a la media al 40.0%. No obstante, extraer hasta 47 factores PCA provocó sobreajuste in-sample, incrementando la dispersión en los periodos de divergencia estructural de 2023.

---

## ADR 013: Configuración Híbrida ("The Sweet Spot") — Arbitraje Estadístico PCA S&P 100
* **Fecha:** 2026-11-01
* **Estado:** Aceptado
* **Contexto:**
  1. La configuración base (ADR 011) ofreció estabilidad factorial (retorno -0.10%, Sharpe -0.03), pero sufrió de permanencia excesiva (33.3% de cierres por fin de trimestre).
  2. La configuración agresiva (ADR 012) elevó `variance_threshold` a 0.87, lo que aumentó los autovectores a 47 provocando sobreajuste in-sample en 2023 (-4.22% retorno).
  3. Se requiere un equilibrio exacto ("The Sweet Spot") que preserve los 20–36 factores macro reales del PCA con la velocidad estricta de salida.
* **Decisión:**
  1. **Estabilidad Factorial:** Revertir `variance_threshold` a `0.80` en `PCAFactorModel`.
  2. **Velocidad de Reversión Estricta:** Mantener `max_half_life` en `12.0` días en `EconometricValidator`.
  3. **Toma de Ganancias Asimétrica:** Mantener `exit_z` en `0.75` en `SignalGenerator`.
  4. **Exportación:** Guardar resultados en `results/*_hybrid.csv` y `.json`.
* **Consecuencias:** Se alcanzó el mejor rendimiento del arbitraje estadístico multivariado: **Retorno neto medio positivo de +0.68% por ventana**, **Ratio de Sharpe positivo de +0.16**, **Drawdown máximo acotado en -10.38%**, tasa de acierto del **47.4%** y un incremento del **14.6% en salidas limpias por reversión a la media** (36.8%) frente a la base.

---

## ADR 014: Experimento Bivariado en Acciones Fortaleza (Top 200 SSD) y Límite de Minería de Datos
* **Fecha:** 2026-11-01
* **Estado:** Aceptado
* **Contexto:** Se exploró regresar al modelo bivariado sobre 30 acciones de alta solidez financiera y bajo riesgo de quiebra ("fortaleza"), preseleccionando los Top 200 pares más sincronizados mediante distancia euclidiana (SSD) y aplicando el rigor econométrico pleno con control FDR ($\alpha = 0.05$) y vida media $\tau_{1/2} \le 12.0$ días.
* **Decisión:** Implementar el script independiente [`run_fortress_pairs.py`](../run_fortress_pairs.py) evaluando 2,310 pares en 15 ventanas Walk-Forward (2021–2025).
* **Hallazgo y Consecuencias:**
  1. Aunque 205 pares exhibieron $p \le 0.05$ en Engle-Granger y 190 tuvieron $\tau_{1/2} \le 12$ días, el procedimiento Benjamini-Hochberg sobre $M = 200$ hipótesis simultáneas exigió un umbral mínimo $p \le \frac{1}{200} \times 0.05 = 0.00025$.
  2. Ningún par alcanzó dicho umbral (el menor p-valor fue $0.00051$). El filtro FDR rechazó sistemáticamente el 100% de los pares, concluyendo que en un universo heterogéneo multiclúster (utilities, alimentos, seguros), las correlaciones por distancia no tienen persistencia estacionaria genuina y son artefactos de minería de datos (*data snooping*).
  3. Esto valida el diseño de protección del sistema: frente a universos amplios y diversos, el modelo multivariado PCA (ADR 013) es superior al bivariado por aislar factores sistemáticos de forma global en lugar de forzar cointegraciones artificiales $A$ vs $B$.

---

## ADR 015: Consolidación Oficial de Producción — Estrategia Principal PCA Híbrida a 10 Años (2015–2025)
* **Fecha:** 2026-11-01
* **Estado:** Aceptado (Configuración Oficial de Producción)
* **Contexto:** Se requirió validar la robustez temporal de la configuración híbrida (*The Sweet Spot*) a lo largo de una década completa (2015-01-01 a 2025-12-31) sobre los 100 componentes del S&P 100 más el proxy ETF SPY, cubriendo 2,765 barras diarias y 39 ventanas Walk-Forward trimestrales fuera de muestra (2016 a 2025).
* **Decisión:**
  1. Establecer `run_trading_pipeline` en `run_pipeline.py` con parámetros oficiales: `variance_threshold = 0.80`, `max_half_life = 12.0`, `exit_z = 0.75`, `fdr_alpha = 0.05`, `start_date = "2015-01-01"`.
  2. Implementar un filtro estricto de completitud histórica in-sample (`is_stock_prices[t].isna().sum() == 0`) para evitar que ofertas públicas o escisiones intermedias (ej. `DOW`, `KHC`, `PYPL`) trunquen la matriz de retornos del PCA.
  3. Almacenar el historial decenal en `data/sp100_prices_10y.csv` y los resultados en `results/walk_forward_pca_sp100_10years.*` y `results/trades_pca_sp100_10years.csv`.
* **Consecuencias y Desempeño a 10 Años:**
  - Evaluó 3,745 residuales candidatos en 39 ventanas OOS.
  - El control FDR protegió al fondo en 25 de las 39 ventanas (64% del tiempo en liquidez al no hallar anomalías estadísticamente genuinas).
  - En las 14 ventanas activas se ejecutaron 38 operaciones con una duración media de 12.3 días.
  - El Drawdown máximo de la década se mantuvo estrictamente acotado en -9.54% gracias a la disciplina del Stop-Loss (-8%) y la evacuación de earnings (26.3% de los trades).
  - Activos destacados como Morgan Stanley (`MS`, +10.73% retorno total, +$12,122 PnL) y Abbott (`ABT`, +6.05% retorno, 100% Win Rate) ratifican la capacidad del modelo para monetizar reversiones idiosincrásicas institucionales.





