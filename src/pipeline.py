"""
Pipeline Integral de Pairs Trading (src/pipeline.py).

Coordina el flujo completo bajo el modelo de embudo (funnel):
1. Ingesta y partición Walk-Forward (data.py / universe.py)
2. Preselección por Distancia SSD (selection.py)
3. Validación Econométrica con Engle-Granger, Johansen, OU y FDR (spread.py)
4. Rastreo dinámico de ratio de cobertura con Filtro de Kalman (spread.py)
5. Generación de señales adaptativas con bandas elásticas GARCH (signals.py)
6. Simulación fuera de muestra con fricciones, impacto y short-borrow fees (backtest.py)
7. Evaluación de métricas completas de rendimiento y riesgo (metrics.py)
"""

from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import numpy as np

from src.universe import UniverseManager
from src.selection import DistancePreselector
from src.spread import EconometricValidator, KalmanSpreadTracker
from src.signals import SignalGenerator
from src.backtest import WalkForwardBacktester, MarketImpactModel
from src.metrics import PerformanceMetrics


class PairsTradingPipeline:
    """
    Controlador central del pipeline cuantitativo de arbitraje estadístico.
    """

    def __init__(
        self,
        top_n_ssd: int = 15,
        coint_pvalue: float = 0.05,
        min_half_life: float = 2.0,
        max_half_life: float = 45.0,
        fdr_alpha: float = 0.05,
        base_entry_z: float = 2.0,
        exit_z: float = 0.5,
        elastic_garch: bool = True,
        initial_capital: float = 100_000.0,
        short_borrow_rate: float = 0.02,
        commission_bps: float = 1.5,
        bid_ask_bps: float = 3.0
    ):
        self.preselector = DistancePreselector(top_n_pairs=top_n_ssd)
        self.validator = EconometricValidator(
            coint_pvalue_threshold=coint_pvalue,
            min_half_life=min_half_life,
            max_half_life=max_half_life,
            fdr_alpha=fdr_alpha
        )
        self.signal_generator = SignalGenerator(
            base_entry_z=base_entry_z,
            exit_z=exit_z,
            elastic_volatility=elastic_garch
        )
        self.impact_model = MarketImpactModel(
            commission_bps=commission_bps,
            bid_ask_spread_bps=bid_ask_bps,
            short_borrow_rate_annual=short_borrow_rate
        )
        self.backtester = WalkForwardBacktester(
            initial_capital=initial_capital,
            impact_model=self.impact_model
        )

    def run_walk_forward(
        self,
        prices_df: pd.DataFrame,
        formation_bars: int = 252,
        trading_bars: int = 63,
        step_bars: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta el protocolo Walk-Forward a través de múltiples ventanas rodantes.

        Args:
            prices_df: Matriz de precios limpios y sincronizados.
            formation_bars: Barras de calibración (In-Sample).
            trading_bars: Barras de prueba (Out-of-Sample).
            step_bars: Paso de avance temporal.

        Returns:
            Dict con bitácora de ventanas, pares operados y métricas consolidadas.
        """
        splits = UniverseManager.get_walk_forward_splits(
            prices_df,
            formation_bars=formation_bars,
            trading_bars=trading_bars,
            step_bars=step_bars
        )

        window_results = []
        all_pair_equities = []

        for window_idx, (df_formation, df_trading) in enumerate(splits):
            # 1. Fase 1: Preselección rápida SSD
            candidates = self.preselector.select_top_candidates(df_formation)
            candidate_pairs = [
                (row["asset_a"], row["asset_b"]) for _, row in candidates.iterrows()
            ]

            # 2. Fase 2: Validación Econométrica (EG + OU + FDR)
            validated_df = self.validator.validate_candidate_pairs(df_formation, candidate_pairs)
            approved_pairs = validated_df[validated_df["is_valid_pair"]] if not validated_df.empty else pd.DataFrame()

            window_record = {
                "window": window_idx,
                "formation_start": df_formation.index[0],
                "formation_end": df_formation.index[-1],
                "trading_start": df_trading.index[0],
                "trading_end": df_trading.index[-1],
                "candidates_ssd_count": len(candidates),
                "validated_pairs_count": len(approved_pairs),
                "traded_pairs": []
            }

            # 3. Operación Out-of-Sample para los pares aprobados
            if not approved_pairs.empty:
                for _, pair_row in approved_pairs.iterrows():
                    a = pair_row["asset_a"]
                    b = pair_row["asset_b"]
                    hl = pair_row["half_life"]

                    p_a_oos = df_trading[a]
                    p_b_oos = df_trading[b]

                    # Filtro de Kalman secuencial en Out-of-Sample
                    kalman = KalmanSpreadTracker()
                    kalman_df = kalman.filter_series(p_a_oos, p_b_oos)
                    spread_oos = kalman_df["spread"]
                    beta_oos = kalman_df["beta"]

                    # Z-Score y Volatilidad condicional
                    z_oos = self.signal_generator.compute_zscore(spread_oos, rolling_window=min(30, len(spread_oos)))
                    garch_vol = self.signal_generator.garch_estimator.estimate_volatility(spread_oos)

                    # Correlación móvil
                    ret_a = p_a_oos.pct_change()
                    ret_b = p_b_oos.pct_change()
                    roll_corr = ret_a.rolling(20, min_periods=5).corr(ret_b).fillna(1.0)

                    # Señales
                    signals_df = self.signal_generator.generate_signals(
                        spread=spread_oos,
                        z_score=z_oos,
                        half_life=hl,
                        rolling_correlation=roll_corr,
                        conditional_vol=garch_vol
                    )

                    # Simulación
                    history_df, trades_df = self.backtester.simulate_pair(
                        prices_a=p_a_oos,
                        prices_b=p_b_oos,
                        signals=signals_df["position"],
                        hedge_ratio=beta_oos
                    )

                    pair_metrics = PerformanceMetrics.calculate_metrics(
                        equity_curve=history_df["net_equity"],
                        gross_equity_curve=history_df["gross_equity"],
                        trades_df=trades_df
                    )

                    window_record["traded_pairs"].append({
                        "pair": f"{a}_{b}",
                        "metrics": pair_metrics,
                        "num_trades": len(trades_df)
                    })

                    all_pair_equities.append(history_df["net_equity"])

            window_results.append(window_record)

        return {
            "num_windows": len(splits),
            "windows": window_results
        }
