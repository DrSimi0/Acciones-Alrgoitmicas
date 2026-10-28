"""
Pruebas unitarias para el motor de backtesting y métricas (src/backtest.py y src/metrics.py).
"""

import pytest
import pandas as pd
import numpy as np

from src.backtest import MarketImpactModel, WalkForwardBacktester
from src.metrics import PerformanceMetrics


class TestMarketImpactModel:

    def test_execution_prices_spread_and_slippage(self):
        model = MarketImpactModel(commission_bps=2.0, bid_ask_spread_bps=10.0, impact_parameter=0.0)
        p_nominal = 100.0

        p_buy = model.calculate_execution_price(p_nominal, is_buy=True)
        p_sell = model.calculate_execution_price(p_nominal, is_buy=False)

        # Medio spread de 10 bps = 5 bps = 0.0005 -> 100.05 compra, 99.95 venta
        assert np.isclose(p_buy, 100.05, atol=1e-4)
        assert np.isclose(p_sell, 99.95, atol=1e-4)

    def test_short_borrow_cost_calculation(self):
        # 2% anual sobre $100,000 nocional por 365.25 días debe ser exactamente $2,000
        model = MarketImpactModel(short_borrow_rate_annual=0.02)
        cost = model.compute_borrow_cost(100_000.0, days=365.25)
        assert np.isclose(cost, 2_000.0, atol=1e-4)


class TestWalkForwardBacktester:

    def test_t_plus_one_execution_rule(self):
        dates = pd.date_range("2023-01-01", periods=5, freq="B")
        prices_a = pd.Series([100.0, 102.0, 104.0, 103.0, 101.0], index=dates)
        prices_b = pd.Series([50.0, 50.5, 51.0, 50.5, 50.0], index=dates)
        # Señal de compra generada en t=1 (segundo día)
        signals = pd.Series([0, 1, 1, 0, 0], index=dates)
        beta = pd.Series([2.0] * 5, index=dates)

        backtester = WalkForwardBacktester(initial_capital=10_000.0)
        history, trades = backtester.simulate_pair(prices_a, prices_b, signals, beta)

        # En t=1 las acciones deben ser 0 (porque la señal se generó al cierre de t=1)
        assert history["shares_a"].iloc[1] == 0.0
        # En t=2 la orden se ejecuta al inicio de la barra (ejecución t+1)
        assert history["shares_a"].iloc[2] != 0.0

    def test_net_equity_lower_than_gross_equity_with_trades(self):
        dates = pd.date_range("2023-01-01", periods=10, freq="B")
        prices_a = pd.Series(100.0 + np.sin(np.linspace(0, 3, 10)), index=dates)
        prices_b = pd.Series(50.0 + np.cos(np.linspace(0, 3, 10)), index=dates)
        signals = pd.Series([0, 1, 1, 0, -1, -1, 0, 0, 0, 0], index=dates)
        beta = pd.Series([1.5] * 10, index=dates)

        backtester = WalkForwardBacktester(initial_capital=50_000.0)
        history, _ = backtester.simulate_pair(prices_a, prices_b, signals, beta)

        # El patrimonio neto final debe ser estrictamente menor o igual que el bruto debido a comisiones y short-borrow
        final_net = history["net_equity"].iloc[-1]
        final_gross = history["gross_equity"].iloc[-1]
        assert final_net < final_gross


class TestPerformanceMetrics:

    def test_metrics_calculation(self):
        dates = pd.date_range("2023-01-01", periods=100, freq="B")
        # Serie alcista con volatilidad
        equity = pd.Series(100_000.0 * (1.0 + np.linspace(0, 0.10, 100)), index=dates)

        metrics = PerformanceMetrics.calculate_metrics(equity)

        assert metrics["initial_capital"] == 100_000.0
        assert np.isclose(metrics["final_capital"], 110_000.0, atol=1e-2)
        assert np.isclose(metrics["total_net_return"], 0.10, atol=1e-4)
        assert metrics["sharpe_ratio"] > 0.0
        assert metrics["max_drawdown"] <= 0.0
