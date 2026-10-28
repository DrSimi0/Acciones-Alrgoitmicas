"""
Pruebas unitarias para los módulos src/data.py y src/universe.py.
"""

import pytest
import pandas as pd
import numpy as np

from src.universe import UniverseManager
from src.data import (
    CorporateActionAdjuster,
    ContinuousFuturesBuilder,
    SyntheticMarketDataGenerator
)


class TestUniverseManager:

    def test_filter_active_tickers(self):
        dates = pd.date_range("2023-01-01", periods=100, freq="D")
        df = pd.DataFrame({
            "STOCK_A": np.linspace(10, 20, 100),
            "STOCK_B": [10.0] * 50 + [np.nan] * 50,  # 50% NaNs
            "STOCK_C": np.linspace(30, 40, 100)
        }, index=dates)

        um = UniverseManager(min_history_bars=80)
        active = um.filter_active_tickers(df, max_nan_ratio=0.05)

        assert "STOCK_A" in active
        assert "STOCK_C" in active
        assert "STOCK_B" not in active

    def test_synchronize_universe(self):
        dates = pd.date_range("2023-01-01", periods=5, freq="D")
        df = pd.DataFrame({
            "STOCK_A": [10.0, np.nan, 12.0, 13.0, 14.0],
            "STOCK_B": [20.0, 21.0, 22.0, 23.0, 24.0]
        }, index=dates)

        um = UniverseManager()
        synced = um.synchronize_universe(df, forward_fill_limit=1)

        assert not synced.isna().any().any()
        assert synced.loc[dates[1], "STOCK_A"] == 10.0  # Relleno hacia adelante

    def test_walk_forward_splits_no_overlap(self):
        dates = pd.date_range("2023-01-01", periods=300, freq="B")
        df = pd.DataFrame({"PRICE": np.arange(300)}, index=dates)

        splits = UniverseManager.get_walk_forward_splits(
            df, formation_bars=100, trading_bars=50, step_bars=50
        )

        assert len(splits) == 4  # (300 - 100) / 50 = 4 ventanas posibles

        for formation, trading in splits:
            assert len(formation) == 100
            assert len(trading) == 50
            # Verificación de no anticipación: la última fecha de formación es estrictamente anterior a la primera de trading
            assert formation.index[-1] < trading.index[0]


class TestCorporateActionAdjuster:

    def test_split_backward_adjustment(self):
        dates = pd.date_range("2023-01-01", periods=4, freq="D")
        raw = pd.Series([100.0, 100.0, 50.0, 50.0], index=dates)
        # Split 2-for-1 en t=2 (el precio cae de 100 a 50)
        splits = pd.Series({dates[2]: 0.5})

        adjusted = CorporateActionAdjuster.adjust_splits_and_dividends(raw, splits=splits)

        # La barra posterior al split conserva el valor nominal
        assert adjusted.iloc[-1] == 50.0
        # Las barras anteriores se escalan a 50.0
        assert adjusted.iloc[0] == 50.0
        assert adjusted.iloc[1] == 50.0


class TestContinuousFuturesBuilder:

    def test_panama_stitch_preserves_differences(self):
        dates = pd.date_range("2023-01-01", periods=6, freq="D")
        # Contrato frontal vence en t=3; cotiza a 100, 102, 104, 106
        c1 = pd.Series([100.0, 102.0, 104.0, 106.0], index=dates[:4])
        # Contrato segundo cotiza con contango de 5 puntos: 109, 111 en rollover t=3
        c2 = pd.Series([111.0, 113.0, 115.0], index=dates[3:])

        stitched = ContinuousFuturesBuilder.panama_stitch([c1, c2], roll_indices=[3])

        # En t=3, el salto (111 - 106 = 5) se restaura aditivamente a c1
        # Las diferencias diarias deben ser idénticas a los contratos subyacentes
        diff_orig_c1 = c1.diff().dropna()
        diff_stitched_c1 = stitched.loc[c1.index[:-1]].diff().dropna()
        np.testing.assert_array_almost_equal(diff_orig_c1.values[:-1], diff_stitched_c1.values)


class TestSyntheticMarketDataGenerator:

    def test_cointegrated_pair_dimensions(self):
        y, x = SyntheticMarketDataGenerator.generate_cointegrated_pair(n_bars=250, seed=42)
        assert len(y) == 250
        assert len(x) == 250
        assert y.index.equals(x.index)
        assert not y.isna().any()
        assert not x.isna().any()

    def test_random_walks_dimensions(self):
        df = SyntheticMarketDataGenerator.generate_random_walks(n_assets=5, n_bars=100)
        assert df.shape == (100, 5)
        assert not df.isna().any().any()
