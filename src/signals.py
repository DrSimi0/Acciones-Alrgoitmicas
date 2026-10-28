"""
Módulo de Generación de Señales de Trading (signals.py).

Implementa:
1. Estandarización Z-Score del residual del spread.
2. Estimación de volatilidad condicional con GARCH(1,1) y mecanismo de respaldo (fallback) a EWMA.
3. Bandas elásticas adaptativas a regímenes de volatilidad.
4. Reglas lógicas de entrada, salida por convergencia, stop-loss por tiempo (Half-Life)
   y stop-loss por quiebre de correlación estructural.
"""

from typing import Dict, Optional, Tuple
import warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize


class GARCH11Estimator:
    """
    Estimador de volatilidad condicional GARCH(1,1) mediante Máxima Verosimilitud (MLE),
    con fallback robusto a EWMA / desviación móvil estándar ante fallos de optimización.
    """

    def __init__(self, fallback_lambda: float = 0.94):
        """
        Args:
            fallback_lambda: Factor de decaimiento para el modelo EWMA de respaldo (RiskMetrics = 0.94).
        """
        self.fallback_lambda = fallback_lambda

    def _ewma_volatility(self, residuals: np.ndarray) -> np.ndarray:
        """
        Calcula la serie de volatilidad condicional mediante EWMA (fallback).
        sigma_t^2 = lambda * sigma_{t-1}^2 + (1 - lambda) * e_{t-1}^2
        """
        n = len(residuals)
        sigma2 = np.zeros(n)
        sample_var = float(np.var(residuals, ddof=1)) if n > 1 else 1.0
        sigma2[0] = sample_var if sample_var > 1e-8 else 1.0

        for t in range(1, n):
            sigma2[t] = self.fallback_lambda * sigma2[t - 1] + (1.0 - self.fallback_lambda) * (residuals[t - 1] ** 2)

        return np.sqrt(np.maximum(sigma2, 1e-8))

    def estimate_volatility(self, residuals: pd.Series, fallback_window: int = 60) -> pd.Series:
        """
        Estima la volatilidad condicional sigma_t. Si la optimización GARCH no converge
        o la solución viola la condición de estacionariedad (alpha + beta >= 1.0),
        activa automáticamente el fallback a EWMA.

        Args:
            residuals: Serie de residuales del spread.
            fallback_window: Ventana mínima para cálculo de varianza muestral.

        Returns:
            pd.Series con sigma_t estimada para cada fecha.
        """
        res_arr = residuals.dropna().values
        dates = residuals.dropna().index
        n = len(res_arr)

        if n < fallback_window:
            # Historial insuficiente para GARCH fiable: usar EWMA directamente
            sigma_ewma = self._ewma_volatility(res_arr)
            return pd.Series(sigma_ewma, index=dates, name="cond_vol")

        # Función de log-verosimilitud negativa para GARCH(1,1)
        # sigma_t^2 = omega + alpha * e_{t-1}^2 + beta * sigma_{t-1}^2
        def neg_log_likelihood(params):
            omega, alpha, beta = params
            if omega <= 0 or alpha < 0 or beta < 0 or (alpha + beta) >= 0.999:
                return 1e10

            sigma2 = np.zeros(n)
            sigma2[0] = np.var(res_arr[:fallback_window])

            for t in range(1, n):
                sigma2[t] = omega + alpha * (res_arr[t - 1] ** 2) + beta * sigma2[t - 1]
                if sigma2[t] <= 1e-9 or np.isnan(sigma2[t]) or np.isinf(sigma2[t]):
                    return 1e10

            # Log-verosimilitud normal
            llk = -0.5 * np.sum(np.log(2 * np.pi) + np.log(sigma2) + (res_arr ** 2) / sigma2)
            return -llk

        # Parámetros iniciales típicos en series financieras
        init_var = float(np.var(res_arr[:fallback_window]))
        init_params = [init_var * 0.05, 0.08, 0.87]
        bounds = [(1e-7, init_var), (1e-6, 0.3), (0.5, 0.99)]

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                opt_res = minimize(
                    neg_log_likelihood,
                    init_params,
                    bounds=bounds,
                    method="L-BFGS-B",
                    options={"maxiter": 200, "ftol": 1e-7}
                )

            if opt_res.success and (opt_res.x[1] + opt_res.x[2] < 0.999):
                omega, alpha, beta = opt_res.x
                sigma2 = np.zeros(n)
                sigma2[0] = np.var(res_arr[:fallback_window])
                for t in range(1, n):
                    sigma2[t] = omega + alpha * (res_arr[t - 1] ** 2) + beta * sigma2[t - 1]
                sigma = np.sqrt(np.maximum(sigma2, 1e-8))
            else:
                # Fallback por no convergencia
                sigma = self._ewma_volatility(res_arr)
        except Exception:
            # Fallback por excepción matemática
            sigma = self._ewma_volatility(res_arr)

        return pd.Series(sigma, index=dates, name="cond_vol")


class SignalGenerator:
    """
    Generador de señales de trading con umbrales elásticos adaptados a regímenes de volatilidad
    y filtros estrictos de salida por timeout (Half-Life) o ruptura estructural de correlación.
    """

    def __init__(
        self,
        base_entry_z: float = 2.0,
        exit_z: float = 0.5,
        max_half_life_multiplier: float = 3.0,
        min_correlation_threshold: float = 0.20,
        elastic_volatility: bool = True
    ):
        """
        Args:
            base_entry_z: Umbral Z base para apertura de posición (+Z para venta, -Z para compra).
            exit_z: Umbral Z para cierre por convergencia (|Z| <= exit_z).
            max_half_life_multiplier: Número máximo de vidas medias antes de cerrar por timeout.
            min_correlation_threshold: Correlación mínima admitida; si cae por debajo, stop de ruptura.
            elastic_volatility: Si es True, amplía el umbral de entrada cuando la volatilidad condicional es alta.
        """
        self.base_entry_z = base_entry_z
        self.exit_z = exit_z
        self.max_half_life_multiplier = max_half_life_multiplier
        self.min_correlation_threshold = min_correlation_threshold
        self.elastic_volatility = elastic_volatility
        self.garch_estimator = GARCH11Estimator()

    def compute_zscore(self, spread: pd.Series, rolling_window: int = 60) -> pd.Series:
        """
        Calcula el Z-Score del spread utilizando ventanas móviles pasadas:
        Z_t = (spread_t - rolling_mean_t) / rolling_std_t.
        """
        roll_mean = spread.rolling(window=rolling_window, min_periods=max(10, rolling_window // 3)).mean()
        roll_std = spread.rolling(window=rolling_window, min_periods=max(10, rolling_window // 3)).std()
        roll_std = roll_std.replace(0, np.nan).bfill().fillna(1.0)

        z = (spread - roll_mean) / roll_std
        return z.fillna(0.0)

    def generate_signals(
        self,
        spread: pd.Series,
        z_score: pd.Series,
        half_life: float,
        rolling_correlation: pd.Series,
        conditional_vol: Optional[pd.Series] = None,
        kalman_breakdown: Optional[pd.Series] = None
    ) -> pd.DataFrame:
        """
        Genera la serie temporal de estados de posición con prevención de look-ahead bias:
        1: Long Spread (Comprar A, Vender B)
        -1: Short Spread (Vender A, Comprar B)
        0: Neutral / Fuera del mercado

        Args:
            spread: Serie del spread de precios.
            z_score: Serie Z-score estandarizada.
            half_life: Vida media estimada en el periodo in-sample.
            rolling_correlation: Correlación móvil contemporánea entre los dos activos.
            conditional_vol: Serie opcional de volatilidad condicional estimada.
            kalman_breakdown: Serie booleana opcional de ruptura estructural del Filtro de Kalman.

        Returns:
            pd.DataFrame con ['position', 'entry_threshold', 'exit_reason', 'bars_in_trade'].
        """
        n = len(z_score)
        dates = z_score.index

        positions = np.zeros(n, dtype=int)
        exit_reasons = ["none"] * n
        bars_in_trade = np.zeros(n, dtype=int)

        # Umbrales dinámicos
        entry_thresholds = np.full(n, self.base_entry_z)
        if self.elastic_volatility and conditional_vol is not None and len(conditional_vol) == n:
            vol_vals = conditional_vol.values
            median_vol = np.nanmedian(vol_vals)
            if median_vol > 1e-6:
                # Expansión elástica: si la volatilidad es 2x la mediana, el umbral Z requerido se expande moderadamente
                vol_ratio = np.clip(vol_vals / median_vol, 0.5, 2.5)
                entry_thresholds = self.base_entry_z * np.sqrt(vol_ratio)

        current_pos = 0
        current_bars = 0
        max_bars_allowed = int(np.ceil(self.max_half_life_multiplier * half_life)) if half_life > 0 else 60

        z_vals = z_score.values
        corr_vals = rolling_correlation.reindex(dates).fillna(1.0).values
        broken_vals = kalman_breakdown.reindex(dates).fillna(False).values if kalman_breakdown is not None else np.zeros(n, dtype=bool)

        for t in range(n):
            z_t = z_vals[t]
            corr_t = corr_vals[t]
            is_broken_t = bool(broken_vals[t])
            threshold_t = entry_thresholds[t]
            reason = "none"

            if current_pos != 0:
                current_bars += 1

                # 1. Stop por ruptura estructural detectada por incertidumbre Kalman
                if is_broken_t:
                    current_pos = 0
                    current_bars = 0
                    reason = "stop_kalman_breakdown"

                # 2. Stop por fractura de correlación estructural
                elif corr_t < self.min_correlation_threshold:
                    current_pos = 0
                    current_bars = 0
                    reason = "stop_structural_break"

                # 3. Stop por tiempo máximo en posición (timeout de Half-Life)
                elif current_bars >= max_bars_allowed:
                    current_pos = 0
                    current_bars = 0
                    reason = "stop_half_life"

                # 4. Salida por convergencia a la media
                elif (current_pos == 1 and z_t >= -self.exit_z) or (current_pos == -1 and z_t <= self.exit_z):
                    current_pos = 0
                    current_bars = 0
                    reason = "convergence"

            else:
                # Regla de Apertura (solo si la correlación se mantiene y no hay ruptura Kalman)
                if not is_broken_t and corr_t >= self.min_correlation_threshold:
                    if z_t <= -threshold_t:
                        current_pos = 1   # Long Spread (infravalorado)
                        current_bars = 1
                    elif z_t >= threshold_t:
                        current_pos = -1  # Short Spread (sobrevalorado)
                        current_bars = 1

            positions[t] = current_pos
            exit_reasons[t] = reason
            bars_in_trade[t] = current_bars

        return pd.DataFrame({
            "position": positions,
            "entry_threshold": entry_thresholds,
            "exit_reason": exit_reasons,
            "bars_in_trade": bars_in_trade
        }, index=dates)
