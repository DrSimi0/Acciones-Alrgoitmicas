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
* **Consecuencias:** Prevención de interrupciones inesperadas en simulaciones extensas.
