"""
Pruebas unitarias para el motor econométrico y validación del spread (src/spread.py).
"""

import pytest
import pandas as pd
import numpy as np

from src.data import SyntheticMarketDataGenerator
from src.spread import EconometricValidator, KalmanSpreadTracker


class TestEconometricValidator:

    def test_engle_granger_cointegrated_pair(self):
        y, x = SyntheticMarketDataGenerator.generate_cointegrated_pair(
            n_bars=600, beta=1.5, alpha=5.0, ou_kappa=0.20, seed=42
        )
        validator = EconometricValidator(coint_pvalue_threshold=0.05)
        res = validator.test_engle_granger(y, x)

        assert res["is_cointegrated"] is True
        assert res["p_value"] < 0.05
        # La estimación de beta debe aproximarse a 1.5
        assert np.isclose(res["beta"], 1.5, atol=0.15)
        assert len(res["residuals"]) == 600

    def test_engle_granger_random_walks(self):
        rng = np.random.default_rng(999)
        dates = pd.date_range("2023-01-01", periods=300, freq="B")
        x = pd.Series(100 + np.cumsum(rng.normal(0, 1, 300)), index=dates)
        y = pd.Series(50 + np.cumsum(rng.normal(0, 1, 300)), index=dates)

        validator = EconometricValidator()
        res = validator.test_engle_granger(y, x)

        # Dos paseos aleatorios independientes no deben ser cointegrados sistemáticamente
        assert res["p_value"] > 0.05

    def test_fit_ornstein_uhlenbeck(self):
        # Simulación directa de un proceso OU con kappa = 0.10 -> Half-life = ln(2)/0.10 ≈ 6.93 barras
        rng = np.random.default_rng(1234)
        n = 1000
        spread = np.zeros(n)
        true_kappa = 0.10
        for t in range(1, n):
            spread[t] = spread[t-1] - true_kappa * spread[t-1] + rng.normal(0, 0.5)

        s_series = pd.Series(spread)
        validator = EconometricValidator()
        ou_res = validator.fit_ornstein_uhlenbeck(s_series, dt=1.0)

        expected_hl = np.log(2.0) / true_kappa
        assert np.isclose(ou_res["kappa"], true_kappa, atol=0.03)
        assert np.isclose(ou_res["half_life"], expected_hl, atol=2.0)

    def test_benjamini_hochberg_fdr(self):
        validator = EconometricValidator(fdr_alpha=0.05)
        # 10 tests: 3 verdaderos descubrimientos (p muy bajos) y 7 nulos (p altos)
        pvals = {
            ("A", "B"): 0.001,
            ("A", "C"): 0.002,
            ("B", "C"): 0.004,
            ("D", "E"): 0.25,
            ("D", "F"): 0.35,
            ("E", "F"): 0.45,
            ("G", "H"): 0.60,
            ("G", "I"): 0.70,
            ("H", "I"): 0.80,
            ("J", "K"): 0.90,
        }
        approved = validator.filter_fdr_benjamini_hochberg(pvals)

        # Los tres primeros deben ser aprobados
        assert ("A", "B") in approved
        assert ("A", "C") in approved
        assert ("B", "C") in approved
        # Los espurios deben ser rechazados
        assert ("D", "E") not in approved
        assert ("J", "K") not in approved


class TestKalmanSpreadTracker:

    def test_kalman_beta_convergence(self):
        rng = np.random.default_rng(77)
        n = 400
        dates = pd.date_range("2023-01-01", periods=n, freq="B")
        x_vals = 50 + np.cumsum(rng.normal(0, 1, n))
        true_beta = 2.0
        true_alpha = 10.0
        y_vals = true_alpha + true_beta * x_vals + rng.normal(0, 0.2, n)

        y = pd.Series(y_vals, index=dates)
        x = pd.Series(x_vals, index=dates)

        tracker = KalmanSpreadTracker(delta=1e-4, observation_variance_r=0.04)
        df_kalman = tracker.filter_series(y, x)

        assert len(df_kalman) == n
        # Al final de la serie, el beta estimado debe converger al true_beta = 2.0
        final_beta = df_kalman["beta"].iloc[-1]
        assert np.isclose(final_beta, true_beta, atol=0.15)
