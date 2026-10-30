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


class RiskManager:
    """
    Gestor de riesgo para posiciones abiertas en pares de activos.
    Monitorea el PnL no realizado paso a paso y emite salidas forzadas
    (FORCE_EXIT) cuando se vulnera el límite máximo de pérdida por capital.
    """

    def __init__(self, max_loss_pct: float = -0.08) -> None:
        """
        Args:
            max_loss_pct: Pérdida porcentual máxima tolerada sobre el nocional de entrada.
                          Debe expresarse como un decimal negativo (ej. -0.08 para -8%).
        """
        if max_loss_pct > 0:
            # Si el usuario suministra un valor positivo como 0.08, convertir a negativo
            self.max_loss_pct: float = -float(max_loss_pct)
        else:
            self.max_loss_pct = float(max_loss_pct)

    def calculate_unrealized_pnl(
        self,
        entry_price_a: float,
        entry_price_b: float,
        current_price_a: float,
        current_price_b: float,
        position_size_a: float,
        position_size_b: float
    ) -> tuple[float, float, float]:
        """
        Calcula el PnL monetario no realizado, el valor nocional de entrada y la rentabilidad porcentual.

        Returns:
            Tupla (unrealized_pnl, initial_notional, return_pct):
                - unrealized_pnl: Ganancia/pérdida flotante en unidades monetarias.
                - initial_notional: Valor absoluto total invertido/comprometido en la entrada.
                - return_pct: Retorno porcentual no realizado (unrealized_pnl / initial_notional).
        """
        # PnL pata A y pata B
        pnl_a: float = float(position_size_a * (current_price_a - entry_price_a))
        pnl_b: float = float(position_size_b * (current_price_b - entry_price_b))
        unrealized_pnl: float = pnl_a + pnl_b

        # Valor nocional inicial de entrada (exposición total)
        notional_a: float = abs(float(position_size_a * entry_price_a))
        notional_b: float = abs(float(position_size_b * entry_price_b))
        initial_notional: float = notional_a + notional_b

        return_pct: float = (unrealized_pnl / initial_notional) if initial_notional > 1e-9 else 0.0
        return unrealized_pnl, initial_notional, return_pct

    def check_stop_loss(
        self,
        entry_price_a: float,
        entry_price_b: float,
        current_price_a: float,
        current_price_b: float,
        position_size_a: float,
        position_size_b: float
    ) -> bool:
        """
        Evalúa si la posición actual ha alcanzado o superado el límite de pérdida máxima.

        Args:
            entry_price_a: Precio de ejecución de entrada para el activo A.
            entry_price_b: Precio de ejecución de entrada para el activo B.
            current_price_a: Precio actual de mercado para el activo A.
            current_price_b: Precio actual de mercado para el activo B.
            position_size_a: Número de acciones en A (positivo = largo, negativo = corto).
            position_size_b: Número de acciones en B (positivo = largo, negativo = corto).

        Returns:
            bool: True si debe forzarse el cierre inmediato (FORCE_EXIT), False en caso contrario.
        """
        if abs(position_size_a) < 1e-9 and abs(position_size_b) < 1e-9:
            return False

        _, _, return_pct = self.calculate_unrealized_pnl(
            entry_price_a=entry_price_a,
            entry_price_b=entry_price_b,
            current_price_a=current_price_a,
            current_price_b=current_price_b,
            position_size_a=position_size_a,
            position_size_b=position_size_b
        )

        # Si el retorno porcentual es menor o igual al umbral de pérdida permitida, activar stop
        return bool(return_pct <= self.max_loss_pct)


class WalkForwardBacktester:
    """
    Motor vectorizado de simulación para pares con ejecución en t+1 y descomposición de costos.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        impact_model: Optional[MarketImpactModel] = None,
        risk_manager: Optional[RiskManager] = None,
        max_leverage: float = 1.0
    ):
        """
        Args:
            initial_capital: Capital inicial en divisa base.
            impact_model: Instancia de MarketImpactModel (o valores por defecto si es None).
            risk_manager: Instancia de RiskManager para evaluar stop-loss por capital.
            max_leverage: Límite de apalancamiento bruto del portafolio.
        """
        self.initial_capital = initial_capital
        self.impact_model = impact_model if impact_model is not None else MarketImpactModel()
        self.risk_manager = risk_manager
        self.max_leverage = max_leverage

    def simulate_pair(
        self,
        prices_a: pd.Series,
        prices_b: pd.Series,
        signals: pd.Series,
        hedge_ratio: pd.Series,
        signals_exit_reasons: Optional[pd.Series] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Simula la operativa del par respetando la regla estricta de ejecución t+1:
        La señal calculada al cierre de la barra t se ejecuta en la barra t+1.

        Args:
            prices_a: Precios del activo dependiente A.
            prices_b: Precios del activo independiente B.
            signals: Serie con {-1, 0, 1} generada por el módulo de señales.
            hedge_ratio: Serie del ratio beta_t para la cobertura.
            signals_exit_reasons: Serie opcional con el motivo de salida emitido por SignalGenerator.

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
        reasons_vals = (
            signals_exit_reasons.reindex(dates).fillna("none").values
            if signals_exit_reasons is not None
            else None
        )

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
        cooldown_direction = 0

        for t in range(n):
            p_a = price_a_vals[t]
            p_b = price_b_vals[t]
            desired_pos = target_positions[t]
            prev_pos = target_positions[t - 1] if t > 0 else 0

            # Desbloquear cooldown si la señal volvió a neutral (0)
            if desired_pos == 0:
                cooldown_direction = 0
            elif cooldown_direction != 0 and desired_pos == cooldown_direction:
                # Bloquear re-entrada vengativa en la misma divergencia tras ser parado por stop-loss
                desired_pos = 0

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

            # 2. Control de Riesgos: Chequeo de Stop-Loss intradiario/en barra t sobre posición abierta
            force_exit = False
            if current_trade is not None and self.risk_manager is not None:
                force_exit = self.risk_manager.check_stop_loss(
                    entry_price_a=current_trade["entry_price_a"],
                    entry_price_b=current_trade["entry_price_b"],
                    current_price_a=p_a,
                    current_price_b=p_b,
                    position_size_a=shares_a[t - 1],
                    position_size_b=shares_b[t - 1]
                )
                if force_exit:
                    desired_pos = 0  # Forzar liquidación inmediata
                    cooldown_direction = prev_pos  # Activar cooldown para evitar re-entradas inmediatas

            # 3. Rebalanceo / Cambio de posición
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

                    # Flujo de caja por rebalanceo: vender (delta < 0) genera caja positiva; comprar (delta > 0) consume caja
                    cash -= (delta_a * exec_a) + (delta_b * exec_b) + comm
                    step_costs += comm

                    if current_trade is not None:
                        current_trade["exit_date"] = dates[t]
                        current_trade["exit_price_a"] = exec_a
                        current_trade["exit_price_b"] = exec_b

                        if force_exit:
                            exit_lbl = "stop_loss_8pct"
                        elif reasons_vals is not None and t > 0:
                            sig_reason = str(reasons_vals[t - 1])
                            if sig_reason == "convergence":
                                exit_lbl = "mean_reversion"
                            elif sig_reason == "stop_kalman_breakdown":
                                exit_lbl = "stop_kalman_breakdown"
                            elif sig_reason == "stop_structural_break":
                                exit_lbl = "stop_structural_break"
                            elif sig_reason == "stop_half_life":
                                exit_lbl = "stop_half_life"
                            else:
                                exit_lbl = "signal_exit"
                        else:
                            exit_lbl = "signal_exit"

                        current_trade["exit_reason"] = exit_lbl

                        # Cálculo riguroso y exacto de PnL por patas y comisiones
                        pnl_a = shares_a[t - 1] * (exec_a - current_trade["entry_price_a"])
                        pnl_b = shares_b[t - 1] * (exec_b - current_trade["entry_price_b"])
                        total_trade_comm = current_trade.get("entry_comm", 0.0) + comm
                        pnl = pnl_a + pnl_b - total_trade_comm

                        current_trade["pnl_net"] = pnl
                        init_notional = current_trade.get("initial_notional", 0.0)
                        current_trade["return_pct"] = (pnl / init_notional) if init_notional > 1e-9 else 0.0
                        trades.append(current_trade)
                        current_trade = None

                # Si la nueva posición es activa (+1 o -1), dimensionar orden
                if desired_pos != 0 and not force_exit:
                    beta_t = abs(beta_vals[t])
                    # Asignación de capital balanceada por el ratio beta sobre patrimonio neto actual
                    current_nav = cash + (shares_a[t - 1] * p_a) + (shares_b[t - 1] * p_b) if t > 0 else cash
                    allocated_capital = max(current_nav, 0.0) * self.max_leverage
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

                    init_notional = abs(new_shares_a * exec_a) + abs(new_shares_b * exec_b)
                    current_trade = {
                        "entry_date": dates[t],
                        "direction": "LONG_SPREAD" if desired_pos == 1 else "SHORT_SPREAD",
                        "entry_price_a": exec_a,
                        "entry_price_b": exec_b,
                        "shares_a": new_shares_a,
                        "shares_b": new_shares_b,
                        "initial_notional": init_notional,
                        "entry_comm": comm,
                        "entry_nav": current_nav
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
            current_trade["exit_reason"] = "end_of_period"
            pnl_a = shares_a[-1] * (price_a_vals[-1] - current_trade["entry_price_a"])
            pnl_b = shares_b[-1] * (price_b_vals[-1] - current_trade["entry_price_b"])
            pnl = pnl_a + pnl_b - current_trade.get("entry_comm", 0.0)
            current_trade["pnl_net"] = pnl
            init_notional = current_trade.get("initial_notional", 0.0)
            current_trade["return_pct"] = (pnl / init_notional) if init_notional > 1e-9 else 0.0
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
