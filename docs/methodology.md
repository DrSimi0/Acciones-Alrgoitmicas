# Marco Metodológico — Statistical Arbitrage & Pairs Trading

Este documento detalla los fundamentos matemáticos y econométricos del sistema de arbitraje estadístico de pares de acciones.

## 1. Arquitectura de Embudo (Funnel)
El universo de $N$ acciones genera $\frac{N(N-1)}{2}$ pares posibles ($\mathcal{O}(N^2)$). Probar cointegración rigurosa en todas las combinaciones es computacionalmente costoso y aumenta drásticamente la probabilidad de falsos descubrimientos. Se aplica un embudo de dos pasos:
1. **Filtro de Distancia (SSD):** Heurística rápida sobre el periodo de formación para aislar los $K$ pares que cotizan más próximos.
2. **Validación Econométrica:** Aplicación de tests de cointegración, velocidad de reversión a la media (Ornstein-Uhlenbeck) y control de Tasa de Falso Descubrimiento (FDR).

---

## 2. Formulación Matemática de los Módulos

### A. Preselección por Suma de Desviaciones Cuadradas (SSD)
Para evitar la distorsión del día inicial $t=0$, se emplean los **log-precios estandarizados** longitudinalmente en el periodo de formación $t \in [1, T]$:
$$s_{i, t} = \frac{\ln(P_{i, t}) - \mu_{\ln(P_i)}}{\sigma_{\ln(P_i)}}$$
La distancia euclidiana al cuadrado (SSD) entre el activo $i$ y el activo $j$ es:
$$\text{SSD}_{i, j} = \sum_{t=1}^{T} (s_{i, t} - s_{j, t})^2$$
Se seleccionan los $K$ pares con menor $\text{SSD}_{i, j}$.

---

### B. Cointegración (Engle-Granger & Johansen)
Para cada par preseleccionado, se evalúa si existe una combinación lineal estacionaria $I(0)$ entre dos series no estacionarias $I(1)$:
$$y_t = \alpha + \beta x_t + \epsilon_t$$
1. **Engle-Granger:** Se estima $\beta$ por Mínimos Cuadrados Ordinarios (OLS) y se aplica el test de Dickey-Fuller Aumentado (ADF) sobre los residuales $\hat{\epsilon}_t$.
2. **Johansen:** Procedimiento multivariado basado en Modelos Vectoriales de Corrección de Errores (VECM) para contrastar el rango de cointegración $r$.

---

### C. Dinámica de Reversión a la Media (Ornstein-Uhlenbeck)
El spread $X_t$ se modela como un proceso estocástico continuo de reversión a la media:
$$dX_t = \kappa (\theta - X_t) dt + \sigma dW_t$$
Donde:
- $\theta$: Media de largo plazo a la que revierte el spread.
- $\kappa$: Velocidad de reversión a la media.
- $\sigma$: Volatilidad de difusión.

En tiempo discreto ($\Delta t = 1$), se formula como un modelo autorregresivo AR(1):
$$X_t = a + b X_{t-1} + \eta_t$$
Con las equivalencias:
$$b = e^{-\kappa \Delta t} \implies \kappa = -\ln(b)$$
$$\theta = \frac{a}{1 - b}$$
El **Half-Life** (vida media esperada del desvío) es:
$$\tau_{1/2} = \frac{\ln(2)}{\kappa}$$
Pares con $\tau_{1/2} > \tau_{\max}$ se descartan por reversión excesivamente lenta.

---

### D. Control de Falsos Descubrimientos (Benjamini-Hochberg FDR)
Al contrastar simultáneamente $M$ pares candidatos, el error de tipo I (falsos positivos) se acumula. Para controlar el FDR a un nivel $\alpha$ (típicamente $5\%$):
1. Se ordenan los p-valores ascendentes: $p_{(1)} \le p_{(2)} \le \dots \le p_{(M)}$.
2. Se localiza el mayor índice $k$ tal que:
$$p_{(k)} \le \frac{k}{M} \alpha$$
3. Se rechazan las hipótesis nulas para todos los pares $i = 1, \dots, k$.

---

### E. Ratio de Cobertura Dinámico (Filtro de Kalman)
En lugar de asumir un $\beta$ estático, se formula el modelo de espacio de estados:
- Ecuación de Medida: $y_t = \alpha_t + \beta_t x_t + v_t, \quad v_t \sim \mathcal{N}(0, R)$
- Ecuación de Transición: $\begin{bmatrix} \alpha_t \\ \beta_t \end{bmatrix} = \begin{bmatrix} \alpha_{t-1} \\ \beta_{t-1} \end{bmatrix} + w_t, \quad w_t \sim \mathcal{N}(0, Q)$
Esto permite adaptar el ratio de cobertura de forma recursiva a medida que llega cada nueva barra, sin fuga de información futura.

---

### F. Bandas Elásticas Adaptativas y Fallback GARCH(1,1)
El residual estandarizado se calcula como:
$$Z_t = \frac{\hat{\epsilon}_t - \mu_t}{\sigma_t}$$
Donde la varianza condicional $\sigma_t^2$ se estima mediante un modelo GARCH(1,1):
$$\sigma_t^2 = \omega + \alpha \hat{\epsilon}_{t-1}^2 + \beta \sigma_{t-1}^2$$
**Mecanismo de Respaldo (*Fallback*):** Ante advertencias o fallos de convergencia (`ConvergenceWarning`), la volatilidad se estima automáticamente mediante EWMA (Media Móvil Ponderada Exponencialmente) con $\lambda = 0.94$.

---

### G. Fricciones de Mercado y Costos de Préstamo
El retorno neto de cada barra descuenta:
1. **Comisión de corretaje:** Tarifa fija o bps por valor transaccionado.
2. **Diferencial Bid-Ask y Deslizamiento (Slippage):** Penalización por impacto en el libro de órdenes (Almgren-Chriss simplificado).
3. **Costo de Préstamo (*Short-Borrow Fee*):** Devengo diario por mantener acciones vendidas en corto:
$$\text{Costo Corto}_t = \text{Valor de la Posición Corta}_t \times \frac{\text{Tasa Anual}}{365.25} \times \Delta t$$
