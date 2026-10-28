"""
Pruebas unitarias para el motor de backtesting y métricas (src/backtest.py y src/metrics.py).
"""

import pytest
import pandas as pd
import numpy as np

from src.backtest import MarketImpactModel, WalkForwardBacktester, RiskManager
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


class TestRiskManager:

    def test_unrealized_pnl_and_stop_loss_trigger(self):
        risk_mgr = RiskManager(max_loss_pct=-0.08)

        # Posición Long Spread: Compramos 100 de A a $100 (+$10,000), Vendemos 200 de B a $50 (-$10,000)
        # Nocional total inicial = $20,000
        # Caso 1: A sube a $102 (+200), B baja a $49 (+200). PnL = +$400 (+2.0%) -> No stop
        assert risk_mgr.check_stop_loss(
            entry_price_a=100.0, entry_price_b=50.0,
            current_price_a=102.0, current_price_b=49.0,
            position_size_a=100.0, position_size_b=-200.0
        ) is False

        # Caso 2: Pérdida menor a 8%: A baja a $98 (-200), B sube a $52 (-400). PnL = -$600 (-3.0%) -> No stop
        assert risk_mgr.check_stop_loss(
            entry_price_a=100.0, entry_price_b=50.0,
            current_price_a=98.0, current_price_b=52.0,
            position_size_a=100.0, position_size_b=-200.0
        ) is False

        # Caso 3: Pérdida excede -8%: Nocional $20,000, 8% son $1,600.
        # A cae a $90 (-$1,000), B sube a $55 (-$1,000). Pérdida = -$2,000 (-10%) -> Debe activar Stop-Loss
        assert risk_mgr.check_stop_loss(
            entry_price_a=100.0, entry_price_b=50.0,
            current_price_a=90.0, current_price_b=55.0,
            position_size_a=100.0, position_size_b=-200.0
        ) is True

    def test_backtester_integrates_risk_manager_force_exit(self):
        dates = pd.date_range("2023-01-01", periods=5, freq="B")
        # Precios donde el par diverge catastróficamente en t=2
        prices_a = pd.Series([100.0, 100.0, 80.0, 70.0, 60.0], index=dates)
        prices_b = pd.Series([50.0, 50.0, 60.0, 65.0, 70.0], index=dates)
        # Señal mantiene posición activa en 1 todo el tiempo
        signals = pd.Series([0, 1, 1, 1, 1], index=dates)
        beta = pd.Series([2.0] * 5, index=dates)

        risk_mgr = RiskManager(max_loss_pct=-0.08)
        backtester = WalkForwardBacktester(initial_capital=100_000.0, risk_manager=risk_mgr)
        history, trades = backtester.simulate_pair(prices_a, prices_b, signals, beta)

        assert not trades.empty
        # Debe haber registrado FORCE_EXIT como motivo de salida
        assert (trades["exit_reason"] == "FORCE_EXIT").any()


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
