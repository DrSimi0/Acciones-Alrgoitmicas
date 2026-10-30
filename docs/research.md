# Registro de Literatura Académica y Fuentes de Referencia

Este archivo documenta las fuentes científicas que sustentan el diseño de la estrategia cuantitativa de arbitraje estadístico de pares.

---

## 1. Gatev, Goetzmann y Rouwenhorst (2006)
* **Título:** *Pairs Trading: Performance of a Relative-Value Arbitrage Rule*
* **Publicación:** The Review of Financial Studies, 19(3), 797–808. DOI: 10.1093/rfs/hhj020.
* **Hipótesis:** Pares de acciones con comovimiento histórico cercano generan rendimientos anormales cuando divergen temporalmente.
* **Método:** Preselección por Suma de Desviaciones Cuadradas (SSD) en periodo de formación (12 meses) y negociación con reglas de Z-score (apertura en 2 desvíos estándar, cierre al converger) durante 6 meses.
* **Conclusiones clave:** Los rendimientos brutos son consistentes pero se degradan significativamente al incorporar costos de transacción y retrasos de ejecución.
* **Aplicación al proyecto:** Sirve como benchmark conceptual V0 y justifica el uso de SSD como filtro rápido de preselección.

---

## 2. Krauss (2017)
* **Título:** *Statistical Arbitrage Pairs Trading Strategies: Review and Outlook*
* **Publicación:** Journal of Economic Surveys, 31(2), 513–545. DOI: 10.1111/joes.12153.
* **Hipótesis:** Comparativa exhaustiva de enfoques de arbitraje estadístico: distancia, cointegración, series temporales (OU/Kalman) y machine learning.
* **Conclusiones clave:** El enfoque de distancia simple decae en mercados modernos con alta eficiencia. Los modelos basados en cointegración y reversión media estructurada presentan mayor robustez económica y menor riesgo de quiebre de par.
* **Aplicación al proyecto:** Estructuración de las versiones evolutivas (V0 a V4) y necesidad de validar con Half-Life y Kalman Filter.

---

## 3. Brunetti y De Luca (2023)
* **Título:** *Pre-selection in cointegration-based pairs trading*
* **Publicación:** Annals of Operations Research. DOI: 10.1007/s10260-023-00702-4.
* **Hipótesis:** La combinación de filtros de correlación/distancia previos al test de cointegración reduce sustancialmente el coste computacional y filtra relaciones espurias.
* **Aplicación al proyecto:** Validación teórica del modelo de embudo (*funnel*): aplicar SSD en `selection.py` antes de las pruebas econométricas costosas en `spread.py`.

---

## 4. Engle y Granger (1987)
* **Título:** *Co-Integration and Error Correction: Representation, Estimation, and Testing*
* **Publicación:** Econometrica, 55(2), 251–276. DOI: 10.2307/1913236.
* **Hipótesis:** Dos series no estacionarias $I(1)$ pueden compartir una tendencia estocástica común, existiendo un vector de cointegración que produce un residuo estacionario $I(0)$.
* **Aplicación al proyecto:** Implementación del test bietápico de Engle-Granger en `spread.py` con valores críticos de MacKinnon.

---

## 5. Benjamini y Hochberg (1995)
* **Título:** *Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing*
* **Publicación:** Journal of the Royal Statistical Society: Series B, 57(1), 289–300.
* **Hipótesis:** En pruebas simultáneas sobre cientos de hipótesis nulas (ej. $\binom{N}{2}$ pares), controlar la tasa de falsos descubrimientos (FDR) equilibra el error Tipo I sin la excesiva severidad destructiva de la corrección de Bonferroni.
* **Evidencia Empírica del Proyecto:** En el universo de mega-caps, relajar FDR al 25% (Experimento A) forzó la aceptación de pares espurios con expectativa negativa (-0.53% retorno medio, Sharpe -0.40). Mantener FDR al 5% en un universo homogéneo de 15 semiconductores (Experimento B) aisló relaciones con sustento económico real (`NVDA/TSM`, `LRCX/NXPI`).

---

## 6. Taleb (2007) y Gestión de Colas Izquierdas en Finanzas Cuantitativas
* **Hipótesis:** Las distribuciones empíricas de activos financieros exhiben colas pesadas y asimetría negativa. Las rupturas estructurales intradía por eventos corporativos (ej. saltos del +25% en earnings de AVGO) no pueden modelarse con normalidad asintótica.
* **Evidencia Empírica del Proyecto:** En el Experimento B (Ventana 12, dic-2024), AVGO registró una explosión del +24.6% en una sola sesión. La intervención determinista del `RiskManager` (Hard Stop-Loss al -8%, ejecutado al -10.33% post-gap) amputó la posición corta inmediatamente, validando que el arbitraje estadístico solo sobrevive a largo plazo si cuenta con límites mecánicos e incondicionales de capital.
