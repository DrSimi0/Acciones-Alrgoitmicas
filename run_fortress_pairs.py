"""
Script Central Coordinador — Experimento Bivariado de Acciones Fortaleza (run_fortress_pairs.py).

Estrategia: Pairs Trading Bivariado (A vs B) sobre un universo de 30 empresas "fortaleza"
con alta resiliencia macroeconómica y bajo riesgo de quiebra.

Arquitectura Cuantitativa:
1. Universo Fortaleza (30 tickers, 435 pares posibles).
2. Preselección SSD: Extracción de los Top-200 pares más sincronizados por ventana in-sample.
3. Rigor Econométrico Acelerado: Cointegración Engle-Granger p <= 0.05, Half-Life OU <= 12.0 días,
   y control FDR Benjamini-Hochberg (alpha = 0.05) sobre los 200 pares evaluados.
4. Estimación Dinámica del Hedge Ratio con Filtro de Kalman secuencial.
5. Ejecución Market-Neutral Long/Short 50/50 (capital_allocation_mode="symmetric_50_50"):
   - Deducción diaria de short-borrow fee (2% anual) sobre la pata corta.
   - Toma de ganancias anticipada en el tramo vertical (exit_z = 0.75).
   - Cuarentena de 3 días y evacuación preventiva con CorporateCalendarManager.
   - Hard Stop-Loss (-8%).
6. Exportación de auditoría completa a results/walk_forward_fortress_200.csv y .json.
"""

import os
import sys
import json
import logging
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd
import numpy as np

from src.data import EquityDataLoader
from src.universe import WalkForwardSplitter
from src.selection import DistancePreselector
from src.spread import EconometricValidator, KalmanSpreadTracker
from src.signals import SignalGenerator
from src.backtest import WalkForwardBacktester, MarketImpactModel, RiskManager, CorporateCalendarManager
from src.metrics import PerformanceEvaluator


# Lista estática de 30 empresas "Fortaleza" (bajo riesgo de quiebra y altos fosos económicos)
FORTRESS_TICKERS = [
    'CLX', 'KMB', 'GIS', 'K', 'SJM', 'HRL', 'CPB', 'CAG', 'HSY', 'CHD',
    'WM', 'RSG', 'FAST', 'CTAS', 'GWW', 'ROP', 'SHW', 'APD', 'ECL', 'PPG',
    'ED', 'SO', 'AEP', 'SRE', 'XEL', 'WEC', 'AWK', 'AFL', 'PRU', 'TRV'
]


def run_fortress_pipeline(
    start_date: str = "2021-01-01",
    end_date: str = "2025-12-31",
    top_n_ssd: int = 200,
    coint_pvalue_threshold: float = 0.05,
    max_half_life: float = 12.0,
    exit_z: float = 0.75,
    fdr_alpha: float = 0.05
) -> None:
    """
    Orquesta el pipeline completo de Pairs Trading Bivariado sobre 30 acciones fortaleza.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.info("Iniciando Pipeline Bivariado de Acciones Fortaleza — Top 200 SSD (30 activos, 435 pares posibles)")

    print("=" * 82)
    print("SISTEMA CUANTITATIVO DE PAIRS TRADING — UNIVERSO FORTALEZA (TOP 200 SSD)")
    print("=" * 82)

    os.makedirs("results", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    prices_cache_path = os.path.join("data", "fortress_prices.csv")

    print(f"\n[1/5] Ingesta de Mercado: {len(FORTRESS_TICKERS)} acciones fortaleza...")
    print(f"      Periodo: {start_date} a {end_date}")

    # Cargar desde caché local si existe
    if os.path.exists(prices_cache_path):
        print("      Cargando historial desde caché local persistente (data/fortress_prices.csv)...")
        prices_df = pd.read_csv(prices_cache_path, index_col=0, parse_dates=True)
    else:
        print("      Descargando precios vía Yahoo Finance...")
        prices_df = EquityDataLoader.load_historical_prices(
            tickers=FORTRESS_TICKERS,
            start_date=start_date,
            end_date=end_date
        )
        prices_df.to_csv(prices_cache_path)
        print("      Datos de mercado guardados en caché local.")

    n_bars, n_assets = prices_df.shape
    total_combinations = int(n_assets * (n_assets - 1) / 2)
    print(f"      Base sincronizada: {n_bars} barras diarias para {n_assets} activos.")
    print(f"      Espacio combinatorio total: {total_combinations} pares posibles por ventana.")

    # 2. Partición temporal Walk-Forward (252 barras In-Sample, 63 barras Out-of-Sample)
    formation_bars = 252
    trading_bars = 63
    step_bars = 63

    print(f"\n[2/5] Particionando historial con WalkForwardSplitter...")
    print(f"      Ventana de formación (In-Sample): {formation_bars} barras (~1 año)")
    print(f"      Ventana de negociación (Out-of-Sample): {trading_bars} barras (~1 trimestre)")

    splits = WalkForwardSplitter.split(
        data=prices_df,
        formation_bars=formation_bars,
        trading_bars=trading_bars,
        step_bars=step_bars
    )
    print(f"      Total de ventanas Walk-Forward generadas: {len(splits)}")

    # 3. Motores Cuantitativos Bivariados
    preselector = DistancePreselector(top_n_pairs=top_n_ssd)
    validator = EconometricValidator(
        coint_pvalue_threshold=coint_pvalue_threshold,
        min_half_life=2.0,
        max_half_life=max_half_life,
        fdr_alpha=fdr_alpha
    )
    signal_gen = SignalGenerator(
        base_entry_z=2.0,
        exit_z=exit_z,
        max_half_life_multiplier=3.0,
        min_correlation_threshold=0.10,
        elastic_volatility=True
    )
    impact_model = MarketImpactModel(
        commission_bps=1.5,
        bid_ask_spread_bps=3.0,
        impact_parameter=0.05,
        short_borrow_rate_annual=0.02
    )
    risk_manager = RiskManager(max_loss_pct=-0.08)

    calendar_manager = CorporateCalendarManager.generate_synthetic_schedule(
        tickers=FORTRESS_TICKERS,
        start_date=start_date,
        end_date=end_date
    )

    backtester = WalkForwardBacktester(
        initial_capital=100_000.0,
        max_leverage=1.0,
        impact_model=impact_model,
        risk_manager=risk_manager,
        calendar_manager=calendar_manager,
        capital_allocation_mode="symmetric_50_50"
    )

    print("\n[3/5] Ejecutando Simulación Walk-Forward Bivariada:")
    print(f"      - Preselección SSD: Top-{top_n_ssd} de {total_combinations} pares por ventana")
    print(f"      - Validación Econométrica: Engle-Granger p <= {coint_pvalue_threshold}, Half-Life <= {max_half_life:.0f}d, FDR = {fdr_alpha:.2f}")
    print(f"      - Ejecución: Long/Short Simétrica 50/50 con devengo de Short-Borrow Fee (2% anual)")
    print(f"      - Señales: Umbral Entry Z = 2.0 (elástico) | Exit Z = {exit_z:.2f} (salida vertical)")

    all_trades_records: List[Dict[str, Any]] = []
    window_logs: List[Dict[str, Any]] = []
    summary_records: List[Dict[str, Any]] = []
    candidates_audit_records: List[Dict[str, Any]] = []

    for window_idx, (formation_df, trading_df) in enumerate(splits, start=1):
        is_start = formation_df.index[0].strftime("%Y-%m-%d")
        is_end = formation_df.index[-1].strftime("%Y-%m-%d")
        oos_start = trading_df.index[0].strftime("%Y-%m-%d")
        oos_end = trading_df.index[-1].strftime("%Y-%m-%d")

        print(f"\n--- Ventana {window_idx:02d}/{len(splits):02d} | In-Sample: {is_start} -> {is_end} | OOS: {oos_start} -> {oos_end} ---")

        # Etapa 1: Preselección Top-200 SSD
        candidates_df = preselector.select_top_candidates(formation_df)
        top_pairs = list(zip(candidates_df["asset_a"], candidates_df["asset_b"]))
        print(f"    [SSD] {len(top_pairs)} pares candidatos extraídos.")

        # Etapa 2: Validación Econométrica Rigurosa con FDR
        audit_df = validator.validate_candidate_pairs(
            candidate_pairs=top_pairs,
            prices_df=formation_df
        )

        if audit_df.empty:
            print("    [Econometría] No se pudieron validar pares.")
            continue

        audit_df["pair"] = list(zip(audit_df["asset_a"], audit_df["asset_b"]))
        audit_df["window_id"] = window_idx
        for _, row in audit_df.iterrows():
            candidates_audit_records.append(row.to_dict())

        valid_pairs_df = audit_df[audit_df["is_valid_pair"] == True]
        valid_pairs = list(zip(valid_pairs_df["asset_a"], valid_pairs_df["asset_b"]))
        print(f"    [Econometría] {len(valid_pairs)}/{len(top_pairs)} pares aprobados (Engle-Granger + OU <= {max_half_life:.0f}d + FDR={fdr_alpha:.2f})")

        if not valid_pairs:
            print("    [-] Sin pares aprobados para negociación en esta ventana OOS.")
            window_logs.append({
                "window": window_idx,
                "in_sample_range": [is_start, is_end],
                "out_of_sample_range": [oos_start, oos_end],
                "candidates_evaluated": len(top_pairs),
                "cointegrated_pairs": 0,
                "trades_count": 0,
                "net_return": 0.0,
                "sharpe": 0.0,
                "max_drawdown": 0.0
            })
            continue

        # Etapa 3: Negociación Bivariada OOS
        window_trades = []
        window_pnl_list = []
        window_metrics_list = []

        for pair in valid_pairs:
            asset_a, asset_b = pair
            p_a_form = formation_df[asset_a]
            p_b_form = formation_df[asset_b]

            # Ajuste de Filtro de Kalman secuencial en ventana de formación
            beta_tracker = KalmanSpreadTracker(delta=1e-4, vt_param=1e-3)
            beta_series_form, spread_series_form, _ = beta_tracker.fit_transform(p_a_form, p_b_form)

            p_a_trade = trading_df[asset_a]
            p_b_trade = trading_df[asset_b]

            # Filtrado online paso a paso en OOS
            beta_trade, spread_trade, _, breakdown_trade = beta_tracker.filter_online(
                p_a_trade, p_b_trade, freeze_beta=False
            )

            # Spread continuo para evitar distorsión en Z-score
            continuous_spread = pd.concat([spread_series_form.iloc[-60:], spread_trade])
            full_zscore = signal_gen.compute_zscore(continuous_spread, rolling_window=60)
            oos_zscore = full_zscore.reindex(trading_df.index).fillna(0.0)

            # Correlación móvil contemporánea entre los dos activos
            rolling_corr = p_a_trade.pct_change().rolling(20, min_periods=5).corr(p_b_trade.pct_change()).bfill().fillna(0.5)

            # Volatilidad condicional estimada vía GARCH/EWMA
            cond_vol = signal_gen.garch_estimator.estimate_volatility(spread_trade.diff().dropna())

            # Vida media in-sample
            hl = float(valid_pairs_df.loc[valid_pairs_df["pair"] == pair, "half_life"].values[0])

            # Generación de señales con salida acelerada (exit_z = 0.75)
            signals_df = signal_gen.generate_signals(
                spread=spread_trade,
                z_score=oos_zscore,
                half_life=hl,
                rolling_correlation=rolling_corr,
                conditional_vol=cond_vol,
                kalman_breakdown=breakdown_trade
            )
            positions = signals_df["position"]

            # Simulación en WalkForwardBacktester (symmetric_50_50)
            hist_df, trades_df = backtester.simulate_pair(
                prices_a=p_a_trade,
                prices_b=p_b_trade,
                signals=positions,
                hedge_ratio=beta_trade,
                signals_exit_reasons=signals_df["exit_reason"],
                ticker_a=asset_a,
                ticker_b=asset_b
            )

            if not hist_df.empty and len(hist_df) >= 2:
                metrics = PerformanceEvaluator.calculate_metrics(
                    equity_curve=hist_df["net_equity"],
                    gross_equity_curve=hist_df["gross_equity"],
                    trades_df=trades_df
                )
                window_metrics_list.append(metrics)
                window_pnl_list.append(metrics.get("total_net_return", 0.0))

            if not trades_df.empty:
                for _, trade_row in trades_df.iterrows():
                    trade_dict = trade_row.to_dict()
                    trade_dict["window_id"] = window_idx
                    trade_dict["pair"] = f"{asset_a}/{asset_b}"
                    window_trades.append(trade_dict)
                    all_trades_records.append(trade_dict)

        avg_ret = float(np.mean(window_pnl_list)) if window_pnl_list else 0.0
        avg_sharpe = float(np.mean([m.get("sharpe_ratio", 0.0) for m in window_metrics_list])) if window_metrics_list else 0.0
        max_dd = float(np.min([m.get("max_drawdown", 0.0) for m in window_metrics_list])) if window_metrics_list else 0.0

        print(f"    [Trading OOS] {len(window_trades)} operaciones ejecutadas.")
        print(f"    [Rendimiento] Retorno Neto: {avg_ret:.2%} | Sharpe: {avg_sharpe:.2f} | Max DD: {max_dd:.2%}")

        w_summary = {
            "window": window_idx,
            "in_sample_range": [is_start, is_end],
            "out_of_sample_range": [oos_start, oos_end],
            "candidates_evaluated": len(top_pairs),
            "cointegrated_pairs": len(valid_pairs),
            "trades_count": len(window_trades),
            "net_return": avg_ret,
            "sharpe": avg_sharpe,
            "max_drawdown": max_dd
        }
        window_logs.append(w_summary)
        summary_records.append({
            "window": window_idx,
            "net_return": avg_ret,
            "sharpe": avg_sharpe,
            "max_drawdown": max_dd,
            "trades": len(window_trades),
            "cointegrated_pairs": len(valid_pairs)
        })

    # 4. Exportación y Resumen Final
    print("\n[4/5] Guardando registros cuantitativos...")

    output_csv = "results/walk_forward_fortress_200.csv"
    output_json = "results/walk_forward_fortress_200.json"
    trades_csv = "results/trades_fortress_200.csv"
    candidates_audit_csv = "results/fortress_200_candidates_audit.csv"

    if summary_records:
        df_summary = pd.DataFrame(summary_records)
        df_summary.to_csv(output_csv, index=False)
        print(f"      Archivo CSV de ventanas guardado: {output_csv}")
    else:
        pd.DataFrame().to_csv(output_csv, index=False)

    if all_trades_records:
        df_trades_all = pd.DataFrame(all_trades_records)
        df_trades_all.to_csv(trades_csv, index=False)
        print(f"      Detalle de operaciones guardado: {trades_csv} ({len(df_trades_all)} trades)")
    else:
        pd.DataFrame().to_csv(trades_csv, index=False)
        print("      No se registraron operaciones en el periodo de backtest.")

    if candidates_audit_records:
        df_audit = pd.DataFrame(candidates_audit_records)
        df_audit.to_csv(candidates_audit_csv, index=False)
        print(f"      Auditoría econométrica guardada: {candidates_audit_csv} ({len(df_audit)} evaluaciones)")

    with open(output_json, "w") as f:
        json.dump(window_logs, f, indent=2)
    print(f"      Log JSON completo guardado: {output_json}")

    print("\n[5/5] Resumen Consolidado Global — Pairs Trading Universo Fortaleza (Top 200 SSD):")
    if summary_records:
        df_sum = pd.DataFrame(summary_records)
        total_trades = df_sum["trades"].sum()
        avg_sharpe = df_sum["sharpe"].mean()
        avg_ret = df_sum["net_return"].mean()
        worst_dd = df_sum["max_drawdown"].min()
        print(f"      Total operaciones ejecutadas OOS : {total_trades}")
        print(f"      Retorno Neto promedio por ventana: {avg_ret:.2%}")
        print(f"      Ratio de Sharpe promedio OOS     : {avg_sharpe:.2f}")
        print(f"      Peor Drawdown registrado         : {worst_dd:.2%}")

    if all_trades_records:
        df_tr = pd.DataFrame(all_trades_records)
        print("\n      Distribución de Motivos de Salida (exit_reason):")
        for reason, count in df_tr["exit_reason"].value_counts().items():
            print(f"        - {reason:<24}: {count:>3} trades ({count / len(df_tr):.1%})")

        if "return_pct" in df_tr.columns:
            wins = (df_tr["return_pct"] > 0).sum()
            win_rate = wins / len(df_tr)
            print(f"      Tasa de Acierto (Win Rate)       : {win_rate:.1%} ({wins}/{len(df_tr)})")

    print("\n" + "=" * 82)
    print("PIPELINE FORTALEZA FINALIZADO CON ÉXITO")
    print("=" * 82)


def main():
    run_fortress_pipeline()


if __name__ == "__main__":
    main()
