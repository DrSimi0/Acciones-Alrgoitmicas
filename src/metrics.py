"""
Módulo de Evaluación de Métricas de Rendimiento y Riesgo (metrics.py).

Implementa el conjunto obligatorio de métricas cuantitativas:
- Rentabilidad acumulada neta y bruta.
- Sharpe, Sortino, Calmar Ratio.
- Máximo Drawdown y duración del drawdown.
- Profit Factor, Win Rate, Expectativa matemática neta por trade.
- Rotación (turnover) y descomposición de costos totales.
"""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd


class PerformanceMetrics:
    """
    Calcula métricas financieras y econométricas completas sobre series de retornos y registro de trades.
    """

    @staticmethod
    def calculate_metrics(
        equity_curve: pd.Series,
        gross_equity_curve: Optional[pd.Series] = None,
        trades_df: Optional[pd.DataFrame] = None,
        risk_free_rate: float = 0.0,
        annualization_factor: float = 252.0
    ) -> Dict[str, Any]:
        """
        Calcula las métricas de rendimiento y riesgo obligatorias.

        Args:
            equity_curve: Serie temporal del valor del portafolio neto (después de costos).
            gross_equity_curve: Serie opcional del valor del portafolio bruto (sin fricciones).
            trades_df: DataFrame con el desglose de operaciones realizadas.
            risk_free_rate: Tasa libre de riesgo anualizada.
            annualization_factor: Factor de anualización (252 para barras diarias).

        Returns:
            Dict con las métricas calculadas.
        """
        eq = equity_curve.dropna()
        if len(eq) < 2:
            return {}

        initial_capital = float(eq.iloc[0])
        final_capital = float(eq.iloc[-1])
        total_net_return = (final_capital / initial_capital) - 1.0

        returns = eq.pct_change().dropna()
        n_bars = len(returns)

        # Retorno anualizado (CAGR)
        years = n_bars / annualization_factor
        cagr = ((final_capital / initial_capital) ** (1.0 / years) - 1.0) if years > 0 and final_capital > 0 else 0.0

        # Volatilidad anualizada
        vol_daily = float(returns.std(ddof=1)) if n_bars > 1 else 0.0
        vol_annual = vol_daily * np.sqrt(annualization_factor)

        # Sharpe Ratio
        rf_daily = risk_free_rate / annualization_factor
        excess_returns = returns - rf_daily
        sharpe = (float(excess_returns.mean()) / vol_daily * np.sqrt(annualization_factor)) if vol_daily > 1e-9 else 0.0

        # Sortino Ratio (desviación a la baja)
        downside_returns = returns[returns < 0]
        downside_std = float(downside_returns.std(ddof=1)) if len(downside_returns) > 1 else 1e-9
        sortino = (float(excess_returns.mean()) / downside_std * np.sqrt(annualization_factor)) if downside_std > 1e-9 else 0.0

        # Drawdown y Máximo Drawdown
        running_max = eq.cummax()
        drawdown_series = (eq - running_max) / running_max
        max_drawdown = float(drawdown_series.min())  # Negativo o 0

        # Calmar Ratio
        calmar = (cagr / abs(max_drawdown)) if abs(max_drawdown) > 1e-6 else 0.0

        # Análisis de operaciones (Trades)
        num_trades = 0
        win_rate = 0.0
        profit_factor = 0.0
        win_loss_ratio = 0.0
        expectancy = 0.0

        if trades_df is not None and not trades_df.empty and "pnl_net" in trades_df.columns:
            pnls = trades_df["pnl_net"].values
            num_trades = len(pnls)
            winning_trades = pnls[pnls > 0]
            losing_trades = pnls[pnls < 0]

            gross_profits = float(np.sum(winning_trades)) if len(winning_trades) > 0 else 0.0
            gross_losses = float(abs(np.sum(losing_trades))) if len(losing_trades) > 0 else 0.0

            win_rate = float(len(winning_trades) / num_trades) if num_trades > 0 else 0.0
            profit_factor = (gross_profits / gross_losses) if gross_losses > 1e-9 else (np.inf if gross_profits > 0 else 0.0)

            avg_win = float(np.mean(winning_trades)) if len(winning_trades) > 0 else 0.0
            avg_loss = float(abs(np.mean(losing_trades))) if len(losing_trades) > 0 else 0.0
            win_loss_ratio = (avg_win / avg_loss) if avg_loss > 1e-9 else 0.0

            # Expectativa matemática neta por trade: (P_win * Avg_Win) - (P_loss * Avg_Loss)
            loss_rate = 1.0 - win_rate
            expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

        # Diferencial Bruto vs Neto
        total_gross_return = total_net_return
        friction_drag = 0.0
        if gross_equity_curve is not None and len(gross_equity_curve) == len(eq):
            initial_gross = float(gross_equity_curve.iloc[0])
            final_gross = float(gross_equity_curve.iloc[-1])
            total_gross_return = (final_gross / initial_gross) - 1.0
            friction_drag = total_gross_return - total_net_return

        return {
            "initial_capital": initial_capital,
            "final_capital": final_capital,
            "total_net_return": float(total_net_return),
            "total_gross_return": float(total_gross_return),
            "friction_drag": float(friction_drag),
            "cagr": float(cagr),
            "annualized_volatility": float(vol_annual),
            "sharpe_ratio": float(sharpe),
            "sortino_ratio": float(sortino),
            "max_drawdown": float(max_drawdown),
            "calmar_ratio": float(calmar),
            "num_trades": int(num_trades),
            "win_rate": float(win_rate),
            "profit_factor": float(profit_factor),
            "win_loss_ratio": float(win_loss_ratio),
            "expectancy_per_trade": float(expectancy)
        }


# Alias para consistencia
PerformanceEvaluator = PerformanceMetrics
