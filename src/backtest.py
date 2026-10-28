"""
Módulo de Simulación y Backtesting Walk-Forward (backtest.py).

Implementa:
1. Modelo de fricción integral: comisiones, diferencial bid-ask, impacto de mercado (Almgren-Chriss)
   y costo continuo de préstamo para posiciones cortas (short-borrow fee).
2. Simulación temporal estricta con ejecución en t+1 (las señales calculadas al cierre de la barra t
   se ejecutan en la apertura/barra t+1).
3. Motor Walk-Forward continuo que concatena los periodos de negociación fuera de muestra.
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd


class MarketImpactModel:
    """
    Modelo de fricciones financieras: comisiones, spread bid-ask, deslizamiento e interés de préstamo.
    """

    def __init__(
        self,
        commission_bps: float = 1.5,
        bid_ask_spread_bps: float = 3.0,
        impact_parameter: float = 0.05,
        short_borrow_rate_annual: float = 0.02
    ):
        """
        Args:
            commission_bps: Comisión de corretaje por transacción en puntos básicos (1 bps = 0.0001).
            bid_ask_spread_bps: Diferencial medio bid-ask en puntos básicos.
            impact_parameter: Parámetro gamma de deslizamiento (Almgren-Chriss) proporcional al tamaño relativo.
            short_borrow_rate_annual: Tasa anual de costo de préstamo de acciones vendidas en corto (2% default).
        """
        self.commission_bps = commission_bps
        self.bid_ask_spread_bps = bid_ask_spread_bps
        self.impact_parameter = impact_parameter
        self.short_borrow_rate_annual = short_borrow_rate_annual

    def calculate_execution_price(
        self,
        nominal_price: float,
        is_buy: bool,
        order_size_shares: float = 100.0,
        average_daily_volume: float = 1_000_000.0
    ) -> float:
        """
        Calcula el precio de ejecución efectivo considerando medio spread y slippage por impacto.
        """
        half_spread = (self.bid_ask_spread_bps / 10000.0) / 2.0

        # Slippage por impacto lineal simplificado
        participation_rate = order_size_shares / max(average_daily_volume, 1.0)
        slippage_bps = self.impact_parameter * np.sqrt(max(0.0, participation_rate))
        total_slippage = half_spread + slippage_bps

        if is_buy:
            return float(nominal_price * (1.0 + total_slippage))
        else:
            return float(nominal_price * (1.0 - total_slippage))

    def compute_commission(self, notional_value: float) -> float:
        """Calcula la comisión en unidades monetarias."""
        return float(abs(notional_value) * (self.commission_bps / 10000.0))

    def compute_borrow_cost(self, short_notional: float, days: float = 1.0) -> float:
        """
        Calcula el interés devengado por mantener acciones vendidas en corto.
        Costo = Valor_Nocional_Corto * (tasa_anual / 365.25) * días
        """
        if short_notional <= 0:
            return 0.0
        return float(short_notional * (self.short_borrow_rate_annual / 365.25) * days)


class WalkForwardBacktester:
    """
    Motor vectorizado de simulación para pares con ejecución en t+1 y descomposición de costos.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        impact_model: Optional[MarketImpactModel] = None,
        max_leverage: float = 1.0
    ):
        """
        Args:
            initial_capital: Capital inicial en divisa base.
            impact_model: Instancia de MarketImpactModel (o valores por defecto si es None).
            max_leverage: Límite de apalancamiento bruto del portafolio.
        """
        self.initial_capital = initial_capital
        self.impact_model = impact_model if impact_model is not None else MarketImpactModel()
        self.max_leverage = max_leverage

    def simulate_pair(
        self,
        prices_a: pd.Series,
        prices_b: pd.Series,
        signals: pd.Series,
        hedge_ratio: pd.Series
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Simula la operativa del par respetando la regla estricta de ejecución t+1:
        La señal calculada al cierre de la barra t se ejecuta en la barra t+1.

        Args:
            prices_a: Precios del activo dependiente A.
            prices_b: Precios del activo independiente B.
            signals: Serie con {-1, 0, 1} generada por el módulo de señales.
            hedge_ratio: Serie del ratio beta_t para la cobertura.

        Returns:
            Tupla (portfolio_history_df, trades_summary_df).
        """
        df = pd.concat([prices_a, prices_b, signals, hedge_ratio], axis=1).dropna()
        df.columns = ["price_a", "price_b", "signal", "beta"]
        dates = df.index
        n = len(df)

        if n < 2:
            return pd.DataFrame(), pd.DataFrame()

        # REGLA DE NO LOOK-AHEAD: Ejecución en t+1 (la posición deseada se desplaza una barra)
        target_positions = df["signal"].shift(1).fillna(0).astype(int).values
        price_a_vals = df["price_a"].values
        price_b_vals = df["price_b"].values
        beta_vals = df["beta"].values

        # Series de seguimiento
        cash = self.initial_capital
        gross_portfolio_val = np.zeros(n)
        net_portfolio_val = np.zeros(n)
        shares_a = np.zeros(n)
        shares_b = np.zeros(n)
        costs_series = np.zeros(n)
        borrow_fee_series = np.zeros(n)

        trades = []
        current_trade = None

        for t in range(n):
            p_a = price_a_vals[t]
            p_b = price_b_vals[t]
            desired_pos = target_positions[t]
            prev_pos = target_positions[t - 1] if t > 0 else 0

            # 1. Devengo del costo de préstamo de cortos sobre la posición abierta del día anterior
            daily_borrow_cost = 0.0
            if t > 0 and (shares_a[t - 1] < 0 or shares_b[t - 1] < 0):
                short_notional = 0.0
                if shares_a[t - 1] < 0:
                    short_notional += abs(shares_a[t - 1] * p_a)
                if shares_b[t - 1] < 0:
                    short_notional += abs(shares_b[t - 1] * p_b)
                daily_borrow_cost = self.impact_model.compute_borrow_cost(short_notional, days=1.0)
                cash -= daily_borrow_cost

            borrow_fee_series[t] = daily_borrow_cost

            # 2. Rebalanceo / Cambio de posición
            step_costs = 0.0
            if desired_pos != prev_pos:
                # Si había una posición previa, cerrarla
                if prev_pos != 0:
                    delta_a = -shares_a[t - 1]
                    delta_b = -shares_b[t - 1]

                    exec_a = self.impact_model.calculate_execution_price(p_a, is_buy=(delta_a > 0))
                    exec_b = self.impact_model.calculate_execution_price(p_b, is_buy=(delta_b > 0))

                    comm = self.impact_model.compute_commission(delta_a * exec_a) + \
                           self.impact_model.compute_commission(delta_b * exec_b)

                    cash += (delta_a * exec_a) + (delta_b * exec_b) - comm
                    step_costs += comm

                    if current_trade is not None:
                        current_trade["exit_date"] = dates[t]
                        current_trade["exit_price_a"] = exec_a
                        current_trade["exit_price_b"] = exec_b
                        current_trade["pnl_net"] = (cash + (shares_a[t-1]*exec_a) + (shares_b[t-1]*exec_b)) - current_trade["entry_nav"]
                        trades.append(current_trade)
                        current_trade = None

                # Si la nueva posición es activa (+1 o -1), dimensionar orden
                if desired_pos != 0:
                    beta_t = abs(beta_vals[t])
                    # Asignación de capital 50/50 balanceada por el ratio beta
                    allocated_capital = cash * self.max_leverage
                    # Monto en A y B: V_A + V_B = allocated_capital, V_B = beta * V_A => V_A = Cap / (1 + beta)
                    nav_a = allocated_capital / (1.0 + beta_t) if (1.0 + beta_t) > 0 else allocated_capital * 0.5
                    nav_b = allocated_capital - nav_a

                    new_shares_a = (nav_a / p_a) * desired_pos
                    new_shares_b = -(nav_b / p_b) * desired_pos  # Posición contraria en B para neutralidad

                    exec_a = self.impact_model.calculate_execution_price(p_a, is_buy=(new_shares_a > 0))
                    exec_b = self.impact_model.calculate_execution_price(p_b, is_buy=(new_shares_b > 0))

                    comm = self.impact_model.compute_commission(new_shares_a * exec_a) + \
                           self.impact_model.compute_commission(new_shares_b * exec_b)

                    cash -= (new_shares_a * exec_a) + (new_shares_b * exec_b) + comm
                    step_costs += comm

                    shares_a[t] = new_shares_a
                    shares_b[t] = new_shares_b

                    current_trade = {
                        "entry_date": dates[t],
                        "direction": "LONG_SPREAD" if desired_pos == 1 else "SHORT_SPREAD",
                        "entry_price_a": exec_a,
                        "entry_price_b": exec_b,
                        "shares_a": new_shares_a,
                        "shares_b": new_shares_b,
                        "entry_nav": cash + (new_shares_a * exec_a) + (new_shares_b * exec_b)
                    }
                else:
                    shares_a[t] = 0.0
                    shares_b[t] = 0.0
            else:
                # Mantener posiciones del día anterior
                shares_a[t] = shares_a[t - 1] if t > 0 else 0.0
                shares_b[t] = shares_b[t - 1] if t > 0 else 0.0

            costs_series[t] = step_costs

            # Valoración a mercado (Mark-to-Market)
            net_val = cash + (shares_a[t] * p_a) + (shares_b[t] * p_b)
            net_portfolio_val[t] = net_val
            gross_portfolio_val[t] = net_val + np.sum(costs_series[:t + 1]) + np.sum(borrow_fee_series[:t + 1])

        # Cerrar posición final abierta si existe al término del periodo
        if current_trade is not None:
            current_trade["exit_date"] = dates[-1]
            current_trade["exit_price_a"] = price_a_vals[-1]
            current_trade["exit_price_b"] = price_b_vals[-1]
            current_trade["pnl_net"] = net_portfolio_val[-1] - current_trade["entry_nav"]
            trades.append(current_trade)

        history_df = pd.DataFrame({
            "net_equity": net_portfolio_val,
            "gross_equity": gross_portfolio_val,
            "shares_a": shares_a,
            "shares_b": shares_b,
            "cash": cash,
            "transaction_costs": costs_series,
            "short_borrow_fee": borrow_fee_series
        }, index=dates)

        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
        return history_df, trades_df
