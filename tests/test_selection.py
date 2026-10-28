"""
Pruebas unitarias para el módulo de preselección por distancia (src/selection.py).
"""

import pytest
import pandas as pd
import numpy as np

from src.selection import DistancePreselector


class TestDistancePreselector:

    def test_normalize_prices_properties(self):
        dates = pd.date_range("2023-01-01", periods=100, freq="D")
        np.random.seed(42)
        prices = pd.DataFrame({
            "STOCK_1": 100.0 * np.exp(np.cumsum(np.random.normal(0, 0.01, 100))),
            "STOCK_2": 50.0 * np.exp(np.cumsum(np.random.normal(0, 0.02, 100)))
        }, index=dates)

        preselector = DistancePreselector()
        norm = preselector.normalize_prices(prices)

        # Cada columna debe tener media 0 y varianza muestral 1
        np.testing.assert_allclose(norm.mean(axis=0), 0.0, atol=1e-12)
        np.testing.assert_allclose(norm.std(axis=0, ddof=1), 1.0, atol=1e-12)

    def test_compute_pairwise_ssd_identical_series(self):
        dates = pd.date_range("2023-01-01", periods=50, freq="D")
        series = np.linspace(10, 20, 50)
        prices = pd.DataFrame({
            "A": series,
            "B": series * 2.0  # Misma trayectoria relativa escalada
        }, index=dates)

        preselector = DistancePreselector()
        norm = preselector.normalize_prices(prices)
        df_ssd = preselector.compute_pairwise_ssd(norm)

        assert len(df_ssd) == 1
        # La correlación debe ser 1.0 y la distancia SSD prácticamente 0.0
        assert np.isclose(df_ssd.loc[0, "correlation"], 1.0, atol=1e-8)
        assert np.isclose(df_ssd.loc[0, "ssd"], 0.0, atol=1e-8)

    def test_select_top_candidates_ranking(self):
        dates = pd.date_range("2023-01-01", periods=100, freq="D")
        rng = np.random.default_rng(101)

        base = np.cumsum(rng.normal(0, 1, 100))
        # Par muy cercano (ruido leve)
        s1 = 100 + base + rng.normal(0, 0.05, 100)
        # Par medianamente cercano
        s2 = 100 + base + rng.normal(0, 0.5, 100)
        # Activo independiente
        s3 = 100 + np.cumsum(rng.normal(0, 1, 100))

        prices = pd.DataFrame({
            "TARGET": 100 + base,
            "NEAR": s1,
            "MEDIUM": s2,
            "INDEP": s3
        }, index=dates)

        preselector = DistancePreselector(top_n_pairs=2)
        top = preselector.select_top_candidates(prices, min_correlation=0.0)

        assert len(top) <= 2
        # El par TARGET y NEAR debe ser el primer clasificado (menor SSD)
        first_pair = set([top.iloc[0]["asset_a"], top.iloc[0]["asset_b"]])
        assert first_pair == {"TARGET", "NEAR"}
