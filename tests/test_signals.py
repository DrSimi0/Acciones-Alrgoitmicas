"""
Pruebas unitarias para el módulo de generación de señales (src/signals.py).
"""

import pytest
import pandas as pd
import numpy as np

from src.signals import GARCH11Estimator, SignalGenerator


class TestGARCH11Estimator:

    def test_garch_volatility_positive_values(self):
        rng = np.random.default_rng(42)
        n = 150
        dates = pd.date_range("2023-01-01", periods=n, freq="B")
        residuals = pd.Series(rng.normal(0, 1.5, n), index=dates)

        estimator = GARCH11Estimator()
        vol = estimator.estimate_volatility(residuals, fallback_window=30)

        assert len(vol) == n
        assert (vol > 0).all()
        assert not vol.isna().any()

    def test_garch_fallback_on_constant_series(self):
        # Serie constante donde la optimización MLE no puede converger normalmente
        dates = pd.date_range("2023-01-01", periods=80, freq="B")
        residuals = pd.Series([0.0] * 80, index=dates)

        estimator = GARCH11Estimator()
        vol = estimator.estimate_volatility(residuals)

        # Debe responder con el fallback sin lanzar excepciones
        assert len(vol) == 80
        assert not vol.isna().any()


class TestSignalGenerator:

    def test_zscore_computation(self):
        dates = pd.date_range("2023-01-01", periods=100, freq="B")
        spread = pd.Series(np.linspace(-5, 5, 100), index=dates)

        generator = SignalGenerator()
        z = generator.compute_zscore(spread, rolling_window=30)

        assert len(z) == 100
        assert not z.isna().any()

    def test_signal_entry_convergence_and_timeout(self):
        dates = pd.date_range("2023-01-01", periods=6, freq="B")
        spread = pd.Series([0.0, -3.0, -1.0, 0.0, 0.0, 0.0], index=dates)
        z_score = pd.Series([0.0, -2.5, -1.0, 0.2, 0.0, 0.0], index=dates)
        corr = pd.Series([0.8] * 6, index=dates)

        generator = SignalGenerator(base_entry_z=2.0, exit_z=0.5, elastic_volatility=False)
        df_sig = generator.generate_signals(
            spread=spread,
            z_score=z_score,
            half_life=10.0,
            rolling_correlation=corr
        )

        # En t=1, Z = -2.5 <= -2.0 -> Debe abrir Long (+1)
        assert df_sig["position"].iloc[1] == 1
        # En t=2, Z = -1.0 -> Mantiene Long (+1)
        assert df_sig["position"].iloc[2] == 1
        # En t=3, Z = 0.2 >= -0.5 -> Cierre por convergencia (exit_reason = 'convergence')
        assert df_sig["exit_reason"].iloc[3] == "convergence"
        assert df_sig["position"].iloc[3] == 0

    def test_signal_stop_structural_break(self):
        dates = pd.date_range("2023-01-01", periods=4, freq="B")
        spread = pd.Series([0.0, -3.0, -3.5, -4.0], index=dates)
        z_score = pd.Series([0.0, -2.5, -2.8, -3.0], index=dates)
        # La correlación cae abruptamente en t=2 rompiendo el umbral de 0.20
        corr = pd.Series([0.9, 0.85, 0.05, 0.0], index=dates)

        generator = SignalGenerator(base_entry_z=2.0, min_correlation_threshold=0.20, elastic_volatility=False)
        df_sig = generator.generate_signals(
            spread=spread,
            z_score=z_score,
            half_life=10.0,
            rolling_correlation=corr
        )

        assert df_sig["position"].iloc[1] == 1
        # En t=2 la correlación es 0.05 < 0.20 -> Stop por ruptura estructural
        assert df_sig["exit_reason"].iloc[2] == "stop_structural_break"
        assert df_sig["position"].iloc[2] == 0
