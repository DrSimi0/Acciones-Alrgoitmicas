"""
Módulo de Motor Econométrico y Validación del Spread (spread.py) — Fase 2 del Embudo.

Implementa:
1. Cointegración Engle-Granger (con valores críticos de MacKinnon) y Johansen (VECM).
2. Modelado Ornstein-Uhlenbeck (AR(1) y MLE) para aislar la tasa de reversión kappa y el Half-Life.
3. Control de Tasa de Falso Descubrimiento (FDR) mediante el procedimiento de Benjamini-Hochberg.
4. Filtro de Kalman paso a paso para estimación online del hedge ratio (beta) sin look-ahead bias.
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from statsmodels.tsa.stattools import coint, adfuller
from statsmodels.tsa.vector_ar.vecm import coint_johansen
import statsmodels.api as sm


class EconometricValidator:
    """
    Validación estadística rigurosa de pares candidatos preseleccionados.
    """

    def __init__(
        self,
        coint_pvalue_threshold: float = 0.05,
        min_half_life: float = 1.0,
        max_half_life: float = 45.0,
        fdr_alpha: float = 0.05
    ):
        """
        Args:
            coint_pvalue_threshold: P-valor máximo admisible para cointegración antes de corrección FDR.
            min_half_life: Vida media mínima en días/barras (evita ruido de microestructura).
            max_half_life: Vida media máxima admisible (evita reversiones inviables para swing trading).
            fdr_alpha: Tasa de falso descubrimiento controlada por Benjamini-Hochberg.
        """
        self.coint_pvalue_threshold = coint_pvalue_threshold
        self.min_half_life = min_half_life
        self.max_half_life = max_half_life
        self.fdr_alpha = fdr_alpha

    def test_engle_granger(self, y: pd.Series, x: pd.Series) -> Dict[str, Any]:
        """
        Ejecuta el test en dos etapas de Engle-Granger:
        1. Regresión OLS: y_t = alpha + beta * x_t + e_t
        2. Test ADF sobre residuales con valores críticos de cointegración (MacKinnon).

        Args:
            y: Serie de precios del activo dependiente.
            x: Serie de precios del activo independiente.

        Returns:
            Dict con beta, alpha, estadístico de cointegración, p-valor y serie de residuales.
        """
        # Alinear datos
        df = pd.concat([y, x], axis=1).dropna()
        y_clean = df.iloc[:, 0].values
        x_clean = df.iloc[:, 1].values

        # Estimación OLS
        X_mat = sm.add_constant(x_clean)
        ols_model = sm.OLS(y_clean, X_mat).fit()
        alpha = float(ols_model.params[0])
        beta = float(ols_model.params[1])

        residuals = pd.Series(y_clean - (alpha + beta * x_clean), index=df.index, name="spread")

        # Test de cointegración con p-valor MacKinnon
        coint_stat, p_value, crit_values = coint(y_clean, x_clean)

        return {
            "beta": beta,
            "alpha": alpha,
            "coint_stat": float(coint_stat),
            "p_value": float(p_value),
            "crit_values": {
                "1%": float(crit_values[0]),
                "5%": float(crit_values[1]),
                "10%": float(crit_values[2])
            },
            "residuals": residuals,
            "is_cointegrated": bool(p_value <= self.coint_pvalue_threshold)
        }

    def test_johansen(self, y: pd.Series, x: pd.Series, det_order: int = 0, k_ar_diff: int = 1) -> Dict[str, Any]:
        """
        Ejecuta la prueba multivariada de Johansen (VECM) para contraste de rango de cointegración.

        Args:
            y, x: Series de precios.
            det_order: Términos deterministas (0 = sin constante en cointegración).
            k_ar_diff: Número de rezagos en diferencias.

        Returns:
            Dict con estadísticos de traza y de máximo autovalor con sus valores críticos al 95%.
        """
        df = pd.concat([y, x], axis=1).dropna()
        res = coint_johansen(df.values, det_order=det_order, k_ar_diff=k_ar_diff)

        # Estadístico de traza para rango r = 0 vs r > 0
        trace_stat_r0 = float(res.lr1[0])
        trace_crit_95_r0 = float(res.cvt[0, 1])

        return {
            "trace_stat": trace_stat_r0,
            "trace_crit_95": trace_crit_95_r0,
            "is_cointegrated_johansen": bool(trace_stat_r0 > trace_crit_95_r0),
            "eigenvalues": [float(val) for val in res.eig]
        }

    def fit_ornstein_uhlenbeck(self, spread: pd.Series, dt: float = 1.0) -> Dict[str, float]:
        """
        Ajusta un proceso Ornstein-Uhlenbeck:
        dX_t = kappa * (theta - X_t) * dt + sigma * dW_t

        Mediante la discretización exacta AR(1):
        X_t = a + b * X_{t-1} + eta_t
        donde b = exp(-kappa * dt), theta = a / (1 - b).
        Half-Life: tau_{1/2} = ln(2) / kappa.

        Args:
            spread: Serie de residuales del par.
            dt: Intervalo temporal entre observaciones (1.0 para barras diarias).

        Returns:
            Dict con kappa, theta, half_life, sigma y R2 de reversión.
        """
        s = spread.dropna().values
        if len(s) < 10:
            return {"kappa": 0.0, "theta": 0.0, "half_life": np.inf, "sigma": 0.0, "r2": 0.0}

        x_prev = s[:-1]
        x_curr = s[1:]

        # Regresión OLS: x_curr = a + b * x_prev
        X = sm.add_constant(x_prev)
        model = sm.OLS(x_curr, X).fit()

        a = float(model.params[0])
        b = float(model.params[1])

        # Si b >= 1.0 o b <= 0.0, no existe reversión a la media continua válida
        if b >= 0.9999 or b <= 0.0:
            kappa = 0.0
            half_life = np.inf
            theta = float(np.mean(s))
        else:
            kappa = -np.log(b) / dt
            half_life = np.log(2.0) / kappa
            theta = a / (1.0 - b)

        residuals_ou = model.resid
        sigma_eta = float(np.std(residuals_ou, ddof=2))
        sigma = sigma_eta / np.sqrt(dt) if kappa > 0 else sigma_eta

        return {
            "kappa": float(kappa),
            "theta": float(theta),
            "half_life": float(half_life),
            "sigma": float(sigma),
            "r2": float(model.rsquared)
        }

    def filter_fdr_benjamini_hochberg(
        self,
        pairs_pvalues: Dict[Tuple[str, str], float]
    ) -> List[Tuple[str, str]]:
        """
        Control de Tasa de Falso Descubrimiento (FDR) mediante el procedimiento Benjamini-Hochberg.

        Args:
            pairs_pvalues: Diccionario {(asset_a, asset_b): p_value}.

        Returns:
            Lista de pares que superan el control FDR.
        """
        if not pairs_pvalues:
            return []

        sorted_pairs = sorted(pairs_pvalues.items(), key=lambda item: item[1])
        m = len(sorted_pairs)
        max_k = -1

        for k, (pair, p_val) in enumerate(sorted_pairs, start=1):
            threshold = (k / m) * self.fdr_alpha
            if p_val <= threshold:
                max_k = k

        if max_k == -1:
            return []

        valid_pairs = [pair for pair, _ in sorted_pairs[:max_k]]
        return valid_pairs

    def validate_candidate_pairs(
        self,
        formation_prices: pd.DataFrame,
        candidate_pairs: List[Tuple[str, str]]
    ) -> pd.DataFrame:
        """
        Pipeline completo de Validación Econométrica (Fase 2 del Embudo):
        1. Test Engle-Granger para cada par candidato.
        2. Estimación OU y filtrado por Half-Life: min_half_life <= tau_1/2 <= max_half_life.
        3. Control FDR Benjamini-Hochberg sobre los pares pre-aprobados.

        Args:
            formation_prices: Precios de formación de los activos.
            candidate_pairs: Lista de tuplas (asset_a, asset_b) provenientes del Top-K de SSD.

        Returns:
            DataFrame con pares validados y sus parámetros econométricos.
        """
        results = []
        p_val_map = {}

        for a, b in candidate_pairs:
            if a not in formation_prices.columns or b not in formation_prices.columns:
                continue

            y = formation_prices[a]
            x = formation_prices[b]

            eg_res = self.test_engle_granger(y, x)
            ou_res = self.fit_ornstein_uhlenbeck(eg_res["residuals"])

            hl = ou_res["half_life"]
            is_hl_valid = (self.min_half_life <= hl <= self.max_half_life)

            record = {
                "asset_a": a,
                "asset_b": b,
                "beta": eg_res["beta"],
                "alpha": eg_res["alpha"],
                "coint_stat": eg_res["coint_stat"],
                "p_value": eg_res["p_value"],
                "kappa": ou_res["kappa"],
                "half_life": hl,
                "sigma": ou_res["sigma"],
                "is_cointegrated": eg_res["is_cointegrated"],
                "is_half_life_valid": is_hl_valid
            }
            results.append(record)
            p_val_map[(a, b)] = eg_res["p_value"]

        if not results:
            return pd.DataFrame()

        df_results = pd.DataFrame(results)

        # Aplicar Benjamini-Hochberg sobre los pares
        fdr_approved = set(self.filter_fdr_benjamini_hochberg(p_val_map))
        df_results["fdr_approved"] = df_results.apply(
            lambda row: (row["asset_a"], row["asset_b"]) in fdr_approved,
            axis=1
        )

        # Criterio final de aprobación: Cointegrado + Half-Life válido + Aprobado por FDR
        df_results["is_valid_pair"] = (
            df_results["is_cointegrated"] &
            df_results["is_half_life_valid"] &
            df_results["fdr_approved"]
        )

        return df_results.sort_values(by="p_value", ascending=True).reset_index(drop=True)


class KalmanSpreadTracker:
    """
    Rastreador dinámico del ratio de cobertura (beta) e intercepto (alpha)
    mediante un Filtro de Kalman en numpy puro, con monitorización continua
    de la covarianza de estado para detectar rupturas estructurales.
    """

    def __init__(
        self,
        delta: float = 1e-4,
        observation_variance_r: float = 1e-3,
        initial_p: float = 1.0,
        breakdown_threshold: float = 5.0
    ) -> None:
        """
        Args:
            delta: Varianza del ruido de proceso del estado (Q).
            observation_variance_r: Varianza del error de medición (R).
            initial_p: Varianza inicial de la matriz de covarianza de estado P_0.
            breakdown_threshold: Umbral crítico para la varianza de beta (P[1, 1]);
                                 si se supera, indica colapso estructural de la relación.
        """
        self.delta: float = float(delta)
        self.r: float = float(observation_variance_r)
        self.breakdown_threshold: float = float(breakdown_threshold)

        # Matriz de covarianza de ruido de proceso Q
        q_scale: float = self.delta / (1.0 - self.delta) if self.delta < 1.0 else 1e-4
        self.Q: np.ndarray = np.eye(2, dtype=np.float64) * q_scale

        # Matriz de covarianza de ruido de medición R
        self.R: float = self.r

        # Estado inicial [alpha, beta]^T
        self.theta: np.ndarray = np.zeros(2, dtype=np.float64)

        # Matriz de covarianza de error del estado P
        self.P: np.ndarray = np.eye(2, dtype=np.float64) * float(initial_p)

    def step(self, y_t: float, x_t: float) -> tuple[float, float, float, bool]:
        """
        Paso secuencial de predicción y actualización (sin look-ahead bias).

        Args:
            y_t: Precio observado del activo dependiente A en tiempo t.
            x_t: Precio observado del activo independiente B en tiempo t.

        Returns:
            Tupla (beta_t, alpha_t, residual_spread_t, is_broken):
                - beta_t: Ratio de cobertura dinámico estimado.
                - alpha_t: Intercepto dinámico estimado.
                - residual_spread_t: Error de predicción (spread residual).
                - is_broken: Flag booleano; True si la varianza de beta (P[1, 1])
                             supera breakdown_threshold.
        """
        # 1. Predicción del estado y covarianza a priori
        theta_pred: np.ndarray = self.theta
        P_pred: np.ndarray = self.P + self.Q

        # 2. Vector de medición H_t = [1, x_t]
        H: np.ndarray = np.array([1.0, float(x_t)], dtype=np.float64)

        # 3. Innovación (error de spread residual)
        y_hat: float = float(np.dot(H, theta_pred))
        error: float = float(y_t - y_hat)

        # 4. Varianza de la innovación S_t = H * P_pred * H^T + R
        S: float = float(np.dot(H, np.dot(P_pred, H)) + self.R)

        # 5. Ganancia de Kalman K_t = P_pred * H^T / S_t
        K: np.ndarray = np.dot(P_pred, H) / S

        # 6. Actualización a posteriori del estado
        self.theta = theta_pred + K * error

        # 7. Actualización a posteriori de la covarianza: P = (I - K * H) * P_pred
        self.P = P_pred - np.outer(K, np.dot(H, P_pred))
        # Garantía de simetría numérica para prevenir derivas de coma flotante
        self.P = 0.5 * (self.P + self.P.T)

        alpha_t: float = float(self.theta[0])
        beta_t: float = float(self.theta[1])
        residual_spread_t: float = error

        # Detección de Ruptura Estructural por incertidumbre en beta
        # Se evalúa la varianza estimada de beta antes o después de la observación
        beta_variance: float = max(float(P_pred[1, 1]), float(self.P[1, 1]))
        is_broken: bool = bool(beta_variance > self.breakdown_threshold)

        return beta_t, alpha_t, residual_spread_t, is_broken

    def update(self, y_t: float, x_t: float) -> tuple[float, float, float]:
        """
        Método de conveniencia para compatibilidad hacia atrás:
        retorna únicamente (beta_t, alpha_t, residual_spread_t).
        """
        beta_t, alpha_t, spread_t, _ = self.step(y_t, x_t)
        return beta_t, alpha_t, spread_t

    def filter_series(self, y: pd.Series, x: pd.Series) -> pd.DataFrame:
        """
        Aplica el filtro secuencialmente a lo largo de toda la serie cronológica.

        Args:
            y, x: Series cronológicas alineadas.

        Returns:
            DataFrame con beta, alpha, spread, beta_variance y is_broken.
        """
        df = pd.concat([y, x], axis=1).dropna()
        y_vals = df.iloc[:, 0].values
        x_vals = df.iloc[:, 1].values
        dates = df.index

        n = len(y_vals)
        betas = np.zeros(n, dtype=np.float64)
        alphas = np.zeros(n, dtype=np.float64)
        spreads = np.zeros(n, dtype=np.float64)
        is_brokens = np.zeros(n, dtype=bool)

        for t in range(n):
            b_t, a_t, s_t, broken_t = self.step(float(y_vals[t]), float(x_vals[t]))
            betas[t] = b_t
            alphas[t] = a_t
            spreads[t] = s_t
            is_brokens[t] = broken_t

        return pd.DataFrame({
            "beta": betas,
            "alpha": alphas,
            "spread": spreads,
            "is_broken": is_brokens
        }, index=dates)
