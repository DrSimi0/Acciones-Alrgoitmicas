"""
Pruebas unitarias para el motor de backtesting y métricas (src/backtest.py y src/metrics.py).
"""

import pytest
import pandas as pd
import numpy as np

from src.backtest import MarketImpactModel, WalkForwardBacktester, RiskManager, CorporateCalendarManager
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
        # Debe haber registrado stop_loss_8pct como motivo de salida
        assert (trades["exit_reason"].isin(["FORCE_EXIT", "stop_loss_8pct"])).any()


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


class TestCorporateCalendarManager:

    def test_synthetic_schedule_generation(self):
        tickers = ["NVDA", "TSM", "AAPL"]
        mgr = CorporateCalendarManager.generate_synthetic_schedule(
            tickers=tickers,
            start_date="2022-01-01",
            end_date="2023-12-31",
            interval_days=90
        )
        for t in tickers:
            dates = mgr.earnings_dates.get(t, [])
            assert len(dates) >= 7  # ~8 trimestres en 2 años
            # Ninguna fecha debe caer en fin de semana
            for d in dates:
                assert d.dayofweek < 5

    def test_is_in_quarantine_and_evacuation_logic(self):
        # 2023-01-10 es Martes
        earnings_date = pd.Timestamp("2023-01-10")
        mgr = CorporateCalendarManager(earnings_dates={"AAA": [earnings_date], "BBB": []})

        # Jueves 2023-01-05: 3 días hábiles hacia adelante son Viernes 06, Lunes 09, Martes 10
        # Está en cuarentena (3 días hábiles)
        assert mgr.is_in_quarantine("AAA", "BBB", pd.Timestamp("2023-01-05")) is True
        # Pero NO requiere evacuación urgente (requiere_evacuation solo mira 1 día hábil adelante)
        assert mgr.requires_evacuation("AAA", "BBB", pd.Timestamp("2023-01-05")) is False

        # Lunes 2023-01-09: El siguiente día hábil es Martes 10 (anuncio de earnings)
        # Requiere evacuación urgente
        assert mgr.requires_evacuation("AAA", "BBB", pd.Timestamp("2023-01-09")) is True
        assert mgr.is_in_quarantine("AAA", "BBB", pd.Timestamp("2023-01-09")) is True

        # Miércoles 2023-01-04: 3 días hábiles son Jueves 05, Viernes 06, Lunes 09. Martes 10 no está.
        assert mgr.is_in_quarantine("AAA", "BBB", pd.Timestamp("2023-01-04")) is False

    def test_backtester_blocks_entry_in_quarantine(self):
        dates = pd.date_range("2023-01-02", periods=6, freq="B")
        # 2023-01-02 Lun, 03 Mar, 04 Mie, 05 Jue, 06 Vie, 09 Lun
        prices_a = pd.Series([100.0] * 6, index=dates, name="AAA")
        prices_b = pd.Series([50.0] * 6, index=dates, name="BBB")
        # Señal de compra en t=1 (Mar 03) -> ejecución t+1 (Mie 04)
        signals = pd.Series([0, 1, 1, 1, 1, 0], index=dates)
        beta = pd.Series([2.0] * 6, index=dates)

        # AAA reporta el Viernes 06.
        # En Mie 04, los próximos 3 días hábiles son Jue 05, Vie 06, Lun 09 -> En cuarentena.
        calendar_mgr = CorporateCalendarManager(earnings_dates={"AAA": [pd.Timestamp("2023-01-06")]})
        backtester = WalkForwardBacktester(initial_capital=100_000.0, calendar_manager=calendar_mgr)

        history, trades = backtester.simulate_pair(prices_a, prices_b, signals, beta, ticker_a="AAA", ticker_b="BBB")

        # La entrada debió ser bloqueada por estar en cuarentena
        assert history["shares_a"].iloc[2] == 0.0
        assert trades.empty

    def test_backtester_evacuates_position_before_earnings(self):
        dates = pd.date_range("2023-01-02", periods=6, freq="B")
        # 2023-01-02 Lun, 03 Mar, 04 Mie, 05 Jue, 06 Vie, 09 Lun
        prices_a = pd.Series([100.0] * 6, index=dates, name="AAA")
        prices_b = pd.Series([50.0] * 6, index=dates, name="BBB")
        # Señal abre en t=0 (Lun 02) -> entra en t=1 (Mar 03)
        signals = pd.Series([1, 1, 1, 1, 1, 0], index=dates)
        beta = pd.Series([2.0] * 6, index=dates)

        # BBB reporta earnings el Lunes 09.
        # En Mar 03 (t=1): los 3 días hábiles de cuarentena son Mie 04, Jue 05, Vie 06 (Lunes 09 NO está -> permite entrada).
        # En Vie 06 (t=4): el próximo día hábil es Lunes 09 -> requiere evacuación preventiva inmediata.
        calendar_mgr = CorporateCalendarManager(earnings_dates={"BBB": [pd.Timestamp("2023-01-09")]})
        backtester = WalkForwardBacktester(initial_capital=100_000.0, calendar_manager=calendar_mgr)

        history, trades = backtester.simulate_pair(prices_a, prices_b, signals, beta, ticker_a="AAA", ticker_b="BBB")

        assert not trades.empty
        # Debe haber salido con motivo FORCE_EXIT_EARNINGS en Vie 06
        assert (trades["exit_reason"] == "FORCE_EXIT_EARNINGS").any()
        assert trades["exit_date"].iloc[0] == pd.Timestamp("2023-01-06")

