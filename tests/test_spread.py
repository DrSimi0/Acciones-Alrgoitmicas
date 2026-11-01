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

    def test_residual_stationarity_ou_vs_random_walk(self):
        rng = np.random.default_rng(888)
        n = 500
        dates = pd.date_range("2023-01-01", periods=n, freq="B")

        # 1. Proceso estacionario (AR(1) con reversión fuerte)
        stationary = np.zeros(n)
        for t in range(1, n):
            stationary[t] = 0.70 * stationary[t-1] + rng.normal(0, 1.0)
        s_series = pd.Series(stationary, index=dates)

        # 2. Paseo aleatorio no estacionario I(1)
        random_walk = np.cumsum(rng.normal(0, 1.0, n))
        rw_series = pd.Series(random_walk, index=dates)

        validator = EconometricValidator(coint_pvalue_threshold=0.05)
        res_stat = validator.test_residual_stationarity(s_series)
        res_rw = validator.test_residual_stationarity(rw_series)

        assert res_stat["is_stationary"] is True
        assert res_stat["p_value"] < 0.01
        assert res_stat["adf_stat"] < res_stat["crit_values"]["5%"]

        assert res_rw["is_stationary"] is False
        assert res_rw["p_value"] > 0.05

    def test_validate_pca_residuals_pipeline(self):
        rng = np.random.default_rng(555)
        n = 400
        dates = pd.date_range("2023-01-01", periods=n, freq="B")

        # Activo 1: Estacionario rápido (Half-Life ~ 3.5 días)
        res_1 = np.zeros(n)
        for t in range(1, n):
            res_1[t] = 0.80 * res_1[t-1] + rng.normal(0, 0.5)

        # Activo 2: Estacionario pero lento (Half-Life ~ 28 días, fuera de max_half_life=15)
        res_2 = np.zeros(n)
        for t in range(1, n):
            res_2[t] = 0.98 * res_2[t-1] + rng.normal(0, 0.5)

        # Activo 3: Paseo aleatorio puro I(1) no estacionario
        rng_rw = np.random.default_rng(999)
        res_3 = np.cumsum(rng_rw.normal(0, 0.5, n))

        df_residuals = pd.DataFrame(
            {"CLEAN_OU": res_1, "SLOW_OU": res_2, "RANDOM_WALK": res_3},
            index=dates
        )

        validator = EconometricValidator(
            coint_pvalue_threshold=0.05,
            min_half_life=1.0,
            max_half_life=15.0,
            fdr_alpha=0.05
        )
        df_val = validator.validate_pca_residuals(df_residuals)

        assert len(df_val) == 3
        # CLEAN_OU debe ser el primer clasificado y ser válido
        row_clean = df_val[df_val["asset"] == "CLEAN_OU"].iloc[0]
        assert bool(row_clean["is_stationary"]) is True
        assert bool(row_clean["is_half_life_valid"]) is True
        assert bool(row_clean["fdr_approved"]) is True
        assert bool(row_clean["is_valid_residual"]) is True

        # SLOW_OU falla por vida media (>45 días)
        row_slow = df_val[df_val["asset"] == "SLOW_OU"].iloc[0]
        assert bool(row_slow["is_half_life_valid"]) is False
        assert bool(row_slow["is_valid_residual"]) is False

        # RANDOM_WALK falla por no ser estacionario
        row_rw = df_val[df_val["asset"] == "RANDOM_WALK"].iloc[0]
        assert bool(row_rw["is_stationary"]) is False
        assert bool(row_rw["is_valid_residual"]) is False


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
        # En datos cointegrados normales no debe haber ruptura estructural
        assert not df_kalman["is_broken"].any()

    def test_kalman_step_and_structural_breakdown_detection(self):
        tracker = KalmanSpreadTracker(breakdown_threshold=2.0)
        
        # Paso normal con varianza inicial
        beta, alpha, error, is_broken = tracker.step(100.0, 50.0)
        assert isinstance(beta, float)
        assert isinstance(alpha, float)
        assert isinstance(error, float)
        assert isinstance(is_broken, bool)
        assert is_broken is False

        # Forzar incremento de incertidumbre P[1, 1] por encima del umbral
        tracker.P[1, 1] = 5.0
        _, _, _, is_broken_after = tracker.step(150.0, 50.0)
        assert is_broken_after is True
