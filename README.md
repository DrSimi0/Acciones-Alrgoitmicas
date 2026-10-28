# Sistema Modular de Pairs Trading & Arbitraje Estadístico

Este repositorio contiene un framework modular para la investigación, filtrado, modelado econométrico y backtesting riguroso de estrategias cuantitativas de arbitraje estadístico (*Pairs Trading*) aplicadas a acciones.

## Características Principales
- **Arquitectura Funnel:** Preselección rápida por distancia euclidiana SSD sobre log-precios estandarizados, seguida de validación econométrica (Engle-Granger, Johansen, Ornstein-Uhlenbeck y FDR Benjamini-Hochberg).
- **Hedge Ratio Dinámico:** Modelado de espacio de estados con Filtro de Kalman.
- **Señales Elásticas:** Bandas dinámicas basadas en volatilidad condicional GARCH(1,1) con fallback automático a EWMA.
- **Simulación Walk-Forward Realista:** Descuento de comisiones, diferencial bid-ask, deslizamiento por impacto de mercado y costo de préstamo de acciones cortas (*short-borrow fees*).
- **Prevención de Sesgos:** Ejecución estricta $t+1$ y división in-sample / out-of-sample sin *look-ahead bias*.

## Estructura del Código
- `src/data.py` & `src/universe.py`: Ingesta *point-in-time*, manejo de eventos corporativos y calendarios de trading.
- `src/selection.py`: Preselección combinatoria por distancia SSD.
- `src/spread.py`: Cointegración, Half-Life y Filtro de Kalman.
- `src/signals.py`: Z-score y umbrales GARCH adaptativos.
- `src/backtest.py`: Motor de ejecución Walk-Forward con modelo de fricciones.
- `src/metrics.py`: Evaluación exhaustiva de rendimiento, riesgo y costos.
- `tests/`: Batería de pruebas unitarias con `pytest`.
- `docs/`: Documentación metodológica, registro de investigación académica y decisiones de arquitectura.
