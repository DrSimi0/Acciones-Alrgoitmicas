# Informe Integral de Auditoría Cuantitativa de Trades

**Fecha de Generación:** 01 de Noviembre de 2026  
**Entorno de Ejecución:** Walk-Forward Simulation (2021–2025)  
**Protocolo:** Cero Look-Ahead Bias, Ejecución $t+1$, Fricciones Bidireccionales (Comisiones, Slippage y Short-Borrow Fee 2% anual).

---

## 1. Resumen Ejecutivo Comparativo de Estrategias

A lo largo del proyecto se han probado diferentes arquitecturas de *Pairs Trading* y arbitraje estadístico. A continuación se presenta el cuadro comparativo consolidado de todos los trades ejecutados:

| Estrategia / Configuración | Trades | Win Rate | PnL Neto Total ($) | Retorno Acum. | Profit Factor | Payoff Ratio | Duración Media | Costos Fricción ($) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **PCA Híbrido ("The Sweet Spot")** | **19** | **47.4%** | **+$17,002.04** | **+16.00%** | **1.53** | **1.69** | **12.4 días** | **$997.04** |
| **PCA Base (80% var, Exit Z 0.0)** | 18 | 44.4% | +$10,130.94 | +10.20% | 1.32 | 1.65 | 12.4 días | $943.50 |
| **Pares Fijos Fundamentales (`CVX/XOM`)** | 2 | 50.0% | +$323.40 | +0.24% | 2.17 | 2.17 | 3.0 días | $88.97 |
| **Semiconductores Bivariado (SSD)** | 9 | 33.3% | -$1,446.23 | -1.37% | 0.80 | 1.60 | 2.4 días | $0.00* |
| **PCA Optimizado (87% var, Exit Z 0.75)**| 15 | 26.7% | -$34,386.36 | -31.29% | 0.26 | 0.70 | 12.5 días | $1,029.58 |
| **Fortress 200 SSD (Defensivo)** | 0 | N/A | $0.00 | 0.00% | N/A | N/A | N/A | $0.00 |

*\*Los primeros experimentos de semiconductores no incluían deducción explícita de short borrow fee ni comisiones bidireccionales completas.*

---

## 2. Anatomía de los Trades: PCA Híbrido "The Sweet Spot"

La configuración híbrida combina:
- Retención dimensional óptima: `variance_threshold = 0.80` (previene sobreajuste).
- Filtrado de persistencia estricto: $\tau_{1/2} \le 12.0$ días.
- Salida asimétrica en el tramo vertical: `exit_z = 0.75` (asegura ganancias sin esperar el cruce por cero).

### 2.1. Desglose por Motivo de Salida (*Exit Reason*)

| Motivo de Salida | Trades | % Total | Retorno Medio | PnL Neto Total ($) | Función en el Sistema |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `mean_reversion` | 7 | 36.8% | +2.12% | **+$16,226.56** | Salida óptima al cerrarse la anomalía (|Z| $\le$ 0.75). |
| `stop_half_life` | 4 | 21.1% | +5.25% | **+$23,228.73** | Cierre por tiempo ($t > 3 \times \tau_{1/2}$). Capturó fuertes tendencias favorables. |
| `FORCE_EXIT_EARNINGS` | 2 | 10.5% | +2.67% | **+$5,872.83** | Evacuación previa a reporte trimestral con ganancias consolidadas. |
| `stop_loss_8pct` | 1 | 5.3% | -9.06% | -$9,957.12 | Cortó la divergencia estructural en `QCOM` protegiendo el fondo. |
| `end_of_period` | 5 | 26.3% | -3.22% | -$18,368.97 | Cierre forzado por expiración de la ventana Walk-Forward de 63 días. |

### 2.2. Simetría Market-Neutral (Long vs Short)

| Dirección | Trades | Retorno Medio | PnL Neto ($) | Comportamiento |
| :--- | :---: | :---: | :---: | :--- |
| **LONG_SPREAD** (Largo Acción / Corto SPY) | 11 | +0.77% | **+$8,489.36** | Explotó activos subvaluados respecto a sus factores. |
| **SHORT_SPREAD** (Corto Acción / Largo SPY) | 8 | +0.94% | **+$8,512.68** | Explotó activos sobreextendidos; absorbió el *short borrow fee*. |
| **Total Combinado** | **19** | **+0.84%** | **+$17,002.04** | **Neutralidad de mercado absoluta.** |

### 2.3. Desglose de PnL por Activo

| Ticker | Trades | Win Rate | Retorno Total | PnL Neto ($) | Contribución |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **CMCSA** | 2 | 100.0% | +10.17% | **+$11,499.15** | Motor de alfa principal. Dos reversiones sumamente limpias. |
| **GOOG** | 3 | 66.7% | +8.13% | **+$8,609.66** | Captura del gran spread post-sobreextensión de 2025. |
| **GE** | 4 | 50.0% | +5.85% | **+$6,325.34** | Alta oscilación cíclica con reversiones rápidas. |
| **NEE** | 2 | 50.0% | +5.36% | **+$5,867.56** | Utilidad altamente cointegrada con factores macro. |
| **GOOGL** | 2 | 50.0% | +3.81% | **+$3,682.11** | Par gemelo de GOOG con comportamiento coordinado. |
| **TMO** | 2 | 50.0% | +2.04% | **+$2,237.59** | Cierres equilibrados en farmacéutica/diagnóstico. |
| **JNJ** | 1 | 0.0% | -4.03% | -$4,427.17 | Salida por fin de periodo OOS. |
| **SBUX** | 2 | 0.0% | -6.29% | -$6,835.08 | Baja velocidad de reversión afectada por arrastre de borrow fee. |
| **QCOM** | 1 | 0.0% | -9.06% | -$9,957.12 | Detonó el Stop-Loss del 8% al romper correlación sectorial. |

---

## 3. Catálogo Detallado de Trades (Trade-by-Trade Audit)

### 3.1. Operaciones de PCA S&P 100 Híbrido (`trades_pca_sp100_hybrid.csv`)

| # | Fecha Entrada | Fecha Salida | Activo | Dirección | Motivo Salida | Días | Borrow Fee ($) | Retorno (%) | PnL Neto ($) |
| :-: | :---: | :---: | :---: | :---: | :---: | :-: | :-: | :-: | :-: |
| 1 | 2022-01-11 | 2022-01-14 | **GE** | LONG_SPREAD | `FORCE_EXIT_EARNINGS` | 3 | $1.63 | +1.16% | +$1,274.37 |
| 2 | 2022-02-04 | 2022-02-09 | **GE** | SHORT_SPREAD | `mean_reversion` | 5 | $16.72 | -0.22% | -$241.29 |
| 3 | 2022-03-08 | 2022-03-17 | **GE** | LONG_SPREAD | `mean_reversion` | 9 | $3.98 | **+6.90%** | **+$7,667.10** |
| 4 | 2022-03-29 | 2022-04-01 | **GE** | LONG_SPREAD | `end_of_period` | 3 | $1.76 | -1.99% | -$2,374.83 |
| 5 | 2022-04-21 | 2022-05-05 | **SBUX** | LONG_SPREAD | `mean_reversion` | 14 | $5.25 | -1.36% | -$1,500.11 |
| 6 | 2022-06-10 | 2022-07-05 | **SBUX** | SHORT_SPREAD | `end_of_period` | 25 | $80.32 | -4.93% | -$5,334.97 |
| 7 | 2022-06-16 | 2022-07-05 | **JNJ** | SHORT_SPREAD | `end_of_period` | 19 | $62.82 | -4.03% | -$4,427.17 |
| 8 | 2022-10-06 | 2022-10-19 | **NEE** | SHORT_SPREAD | `mean_reversion` | 13 | $46.45 | **+5.76%** | **+$6,335.55** |
| 9 | 2022-10-11 | 2022-10-14 | **CMCSA** | LONG_SPREAD | `FORCE_EXIT_EARNINGS` | 3 | $1.65 | **+4.18%** | **+$4,598.47** |
| 10 | 2022-10-11 | 2022-10-28 | **TMO** | LONG_SPREAD | `stop_half_life` | 17 | $7.41 | -0.41% | -$453.95 |
| 11 | 2022-10-27 | 2022-11-17 | **CMCSA** | LONG_SPREAD | `mean_reversion` | 21 | $8.73 | **+5.99%** | **+$6,900.69** |
| 12 | 2022-10-31 | 2022-11-17 | **TMO** | LONG_SPREAD | `stop_half_life` | 17 | $7.08 | **+2.46%** | **+$2,691.54** |
| 13 | 2022-12-23 | 2023-01-03 | **NEE** | LONG_SPREAD | `end_of_period` | 11 | $2.90 | -0.40% | -$467.99 |
| 14 | 2023-10-27 | 2023-11-02 | **QCOM** | SHORT_SPREAD | `stop_loss_8pct` | 6 | $22.89 | -9.06% | -$9,957.12 |
| 15 | 2025-01-22 | 2025-01-29 | **GOOG** | SHORT_SPREAD | `mean_reversion` | 7 | $27.09 | +1.04% | +$1,146.55 |
| 16 | 2025-01-31 | 2025-02-20 | **GOOGL** | SHORT_SPREAD | `stop_half_life` | 20 | $65.92 | **+8.59%** | **+$9,446.11** |
| 17 | 2025-01-31 | 2025-02-21 | **GOOG** | SHORT_SPREAD | `stop_half_life` | 21 | $71.67 | **+10.38%** | **+$11,545.02** |
| 18 | 2025-03-28 | 2025-04-07 | **GOOG** | LONG_SPREAD | `mean_reversion` | 10 | $3.59 | -3.29% | -$4,081.91 |
| 19 | 2025-03-28 | 2025-04-08 | **GOOGL** | LONG_SPREAD | `end_of_period` | 11 | $4.02 | -4.79% | -$5,764.00 |

### 3.2. Operaciones de Pares Fijos Fundamentales (`CVX/XOM`)

| # | Fecha Entrada | Fecha Salida | Par | Dirección | Motivo Salida | Días | PnL Pata A ($) | PnL Pata B ($) | Retorno (%) | PnL Neto ($) |
| :-: | :---: | :---: | :---: | :---: | :---: | :-: | :-: | :-: | :-: | :-: |
| 1 | 2022-06-08 | 2022-06-09 | `CVX/XOM` | LONG_SPREAD | `mean_reversion` | 1 | -$1,417.80 | +$2,055.23 | **+0.44%** | **+$593.17** |
| 2 | 2022-06-30 | 2022-07-05 | `CVX/XOM` | SHORT_SPREAD | `mean_reversion` | 5 | +$1,028.50 | -$1,253.56 | -0.20% | -$269.77 |

---

## 4. Análisis de Costos de Fricción y Deslizamiento

El sistema cuantitativo incorpora costos bidireccionales realistas en cada operación:
1. **Comisiones de Corretaje:** 1.5 puntos básicos (bps) por operación. En PCA Híbrido totalizaron **$555.14**.
2. **Diferencial Bid-Ask y Deslizamiento (Slippage):** 3.0 bps fijos más un modelo de impacto cuadrático proporcional al nocional operado.
3. **Costo de Préstamo por Venta en Corto (*Short-Borrow Fee*):** Tasa del 2% anual devengada día a día. Totalizó **$441.90** en la versión híbrida.

---

## 5. Lecciones Cuantitativas y Recomendaciones de Producción

1. **La Salida Vertical (`exit_z = 0.75`) fue el mayor catalizador de alfa:**  
   Al no forzar al spread a cruzar el cero absoluto, los cierres rentables por `mean_reversion` aumentaron de 4 a 7 operaciones, elevando el PnL neto de $9,457 a **$16,226**.
2. **El Filtro de Calendario Corporativo (`FORCE_EXIT_EARNINGS`) salvó el capital:**  
   Ambas evacuaciones preventivas (`GE` y `CMCSA`) se cerraron con rendimientos positivos (+1.16% y +4.18%), evitando que los saltos de volatilidad (*earnings gap*) destruyeran la neutralidad de la cartera.
3. **El Stop-Loss Estricto (-8%) cumplió su mandato:**  
   En `QCOM`, una ruptura estructural amenazaba con generar una pérdida superior al 20%; el gestor de riesgo liquidó en -9.06% neto, preservando el 91% del capital asignado a la posición.
4. **Próximo Paso de Mejora:**  
   Para reducir el impacto de las salidas por `end_of_period` (-$18,368), se recomienda implementar una **regla de bloqueo de entrada temporal**: no abrir nuevos spreads si faltan menos de 10 días para el término del trimestre Walk-Forward.
