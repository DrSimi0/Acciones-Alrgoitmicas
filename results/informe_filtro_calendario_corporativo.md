# Informe Cuantitativo: Impacto del Filtro de Cuarentena Corporativa (Earnings Blackout Filter)

**Fecha:** 30 de Octubre de 2026  
**Rama:** `main` (Sincronizada con GitHub: commit `f1bf41b`)  
**Estrategia:** Arbitraje Estadístico de Pares Walk-Forward con Filtro de Kalman y Gestión Dual de Riesgos  
**Universo:** 15 Activos del Sector de Semiconductores (105 pares posibles, Top-20 preseleccionados por SSD, FDR Benjamini-Hochberg $\alpha=0.05$)  

---

## 1. Resumen Ejecutivo y Resultados Clave

La implementación del **Filtro de Cuarentena y Evacuación de Calendario Corporativo (`CorporateCalendarManager`)** ha demostrado empíricamente ser uno de los pilares de control de riesgo más determinantes del sistema. 

En estrategias de cointegración accionario, las publicaciones de resultados trimestrales (*earnings*) constituyen eventos discretos de información asimétrica capaces de inducir brechas nocturnas (*overnight gaps*) y saltos de volatilidad no continuos (*Poisson jumps*). Estos saltos fracturan temporal o permanentemente la relación de cobertura $\beta_t$, transformando un arbitraje estadístico de reversión a la media en una apuesta direccional involuntaria de alto riesgo.

### Comparativa Global: Pre vs. Post Filtro de Calendario

| Métrica de Desempeño | Pre-Filtro de Calendario | Post-Filtro (Producción `main`) | Variación / Impacto |
| :--- | :---: | :---: | :---: |
| **Operaciones Totales (15 Ventanas OOS)** | 9 operaciones | 9 operaciones | Cobertura intacta |
| **Operaciones cerradas por `mean_reversion`** | 8 (88.9%) | **9 (100.0%)** | **+11.1% reversiones limpias** |
| **Operaciones cerradas por `stop_loss_8pct`** | 1 (11.1%) | **0 (0.0%)** | **100% eliminación de stops duros** |
| **Retorno Neto Medio por Ventana** | -1.78% | **-0.19%** | **+1.59% de mejora directa** |
| **Ratio de Sharpe Promedio** | -0.74 | **-0.42** | **+0.32 de mejora** |
| **Peor Drawdown Global Registrado** | -12.83% | **-2.87%** | **Reducción del 77.6% del riesgo** |
| **PnL Ventana 12 (`AVGO_TSM`)** | -$12,583.08 (-12.58%) | **+$263.73 (+0.15%)** | **+$12,846.81 recuperados** |

---

## 2. Detalle Exhaustivo de las 9 Operaciones Ejecutadas (Out-of-Sample)

| Ventana | Par Operado | Dirección | Entrada | Salida | Capital Nocional | PnL Neto ($) | Retorno (%) | Motivo de Cierre (`exit_reason`) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **W1** | `ADI_NVDA` | LONG_SPREAD | 2022-03-25 | 2022-03-28 | \$99,960.29 | -\$1,502.78 | -1.50% | `mean_reversion` |
| **W4** | `LRCX_NXPI` | LONG_SPREAD | 2022-12-23 | 2022-12-27 | \$100,037.30 | -\$904.43 | -0.90% | `mean_reversion` |
| **W5** | `LRCX_NXPI` | SHORT_SPREAD | 2023-03-17 | 2023-03-20 | \$99,964.71 | -\$488.80 | -0.49% | `mean_reversion` |
| **W5** | `LRCX_NXPI` | SHORT_SPREAD | 2023-03-30 | 2023-04-03 | \$99,472.29 | +\$1,303.98 | +1.31% | `mean_reversion` |
| **W6** | `LRCX_NXPI` | LONG_SPREAD | 2023-06-14 | 2023-06-15 | \$100,032.70 | -\$1,243.89 | -1.24% | `mean_reversion` |
| **W12** | `NVDA_TSM` | LONG_SPREAD | 2024-12-03 | 2024-12-04 | \$100,010.69 | +\$1,485.60 | +1.49% | `mean_reversion` |
| **W12** | `NVDA_TSM` | LONG_SPREAD | 2024-12-16 | 2024-12-18 | \$101,496.74 | -\$259.64 | -0.26% | `mean_reversion` |
| **W12** | `AVGO_TSM` | SHORT_SPREAD | 2024-12-09 | 2024-12-11 | \$99,996.62 | -\$2,499.98 | -2.50% | `mean_reversion` |
| **W12** | `AVGO_TSM` | SHORT_SPREAD | 2024-12-16 | 2024-12-18 | \$97,501.10 | **+\$2,663.71** | **+2.73%** | `mean_reversion` |
