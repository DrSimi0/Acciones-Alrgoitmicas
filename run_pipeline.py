"""
Script Central Coordinador — Experimento B: Dimensionalidad Sectorial (run_pipeline.py).

Rama: exp-sector-semis
Objetivo:
Expandir la superficie de búsqueda del arbitraje estadístico hacia un universo sectorial denso
de 15 activos de semiconductores (105 pares posibles), manteniendo el máximo rigor econométrico
(coint_pvalue_threshold=0.05, fdr_alpha=0.05, max_half_life=30.0).
"""

import os
import json
import logging
import pandas as pd
import numpy as np

from src.data import EquityDataLoader
from src.universe import WalkForwardSplitter
from src.selection import DistancePreselector
from src.spread import EconometricValidator, KalmanSpreadTracker
from src.signals import SignalGenerator
from src.backtest import WalkForwardBacktester, MarketImpactModel, RiskManager
from src.metrics import PerformanceEvaluator


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.info("Universo Expandido de Semiconductores (15 activos, 105 pares) - Rigor Econométrico Completo (FDR=0.05)")

    print("=" * 78)
    print("EXPERIMENTO B: DIMENSIONALIDAD SECTORIAL EN SEMICONDUCTORES (15 ACTIVOS, FDR=0.05)")
    print("=" * 78)

    os.makedirs("results", exist_ok=True)

    # 1. Ingesta de Datos con EquityDataLoader para el sector Semiconductores
    semis_tickers = [
        "NVDA", "AMD", "AVGO", "TSM", "ASML",
        "QCOM", "TXN", "AMAT", "INTC", "MU",
        "LRCX", "ADI", "KLAC", "NXPI", "MRVL"
    ]
    start_date = "2021-01-01"
    end_date = "2025-12-31"

    print(f"\n[1/5] Descargando precios reales vía yfinance ({len(semis_tickers)} activos)...")
    print(f"      Activos: {', '.join(semis_tickers)}")
    print(f"      Periodo: {start_date} a {end_date}")

    prices_df = EquityDataLoader.load_historical_prices(
        tickers=semis_tickers,
        start_date=start_date,
        end_date=end_date
    )

    n_bars, n_assets = prices_df.shape
    total_combinations = int(n_assets * (n_assets - 1) / 2)
    print(f"      Descarga completada: {n_bars} barras diarias sincronizadas.")
    print(f"      Pares combinatorios posibles por ventana: {total_combinations}")

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

    # 3. Inicialización de Componentes: Máximo Rigor Econométrico sobre Universo Denso
    preselector = DistancePreselector(top_n_pairs=20)  # Ampliado a 20 debido a los 105 pares
    validator = EconometricValidator(
        coint_pvalue_threshold=0.05,  # Rigor estricto del 5%
        min_half_life=2.0,
        max_half_life=30.0,           # Exigencia de reversión ágil (<= 30 días)
        fdr_alpha=0.05                # Control estricto de FDR al 5%
    )
    signal_gen = SignalGenerator(
        base_entry_z=2.0,
        exit_z=0.5,
        elastic_volatility=True
    )
    impact_model = MarketImpactModel(
        commission_bps=1.5,
        bid_ask_spread_bps=3.0,
        impact_parameter=0.05,
        short_borrow_rate_annual=0.02
    )
    risk_manager = RiskManager(max_loss_pct=-0.08)  # Hard Stop-Loss del -8%
    backtester = WalkForwardBacktester(
        initial_capital=100_000.0,
        impact_model=impact_model,
        risk_manager=risk_manager,
        max_leverage=1.0
    )

    # 4. Ejecución del Funnel Ventana por Ventana
    print("\n[3/5] Ejecutando Funnel Cuantitativo (SSD Top-20 -> Econometría FDR=0.05 -> Kalman -> Riesgo)...")
    summary_records = []
    window_logs = []
    all_candidates_audit = []
    all_trades_records = []

    for w_idx, (df_formation, df_trading) in enumerate(splits):
        f_start = df_formation.index[0].strftime("%Y-%m-%d")
        f_end = df_formation.index[-1].strftime("%Y-%m-%d")
        t_start = df_trading.index[0].strftime("%Y-%m-%d")
        t_end = df_trading.index[-1].strftime("%Y-%m-%d")

        print(f"\n>>> VENTANA {w_idx + 1}/{len(splits)} <<<")
        print(f"    Formación (IS) : {f_start} -> {f_end} ({len(df_formation)} barras)")
        print(f"    Trading (OOS)  : {t_start} -> {t_end} ({len(df_trading)} barras)")

        # Paso 1: Preselección por Diferencia SSD (Top-20 pares)
        candidates_df = preselector.select_top_candidates(df_formation)
        candidate_pairs = [
            (row["asset_a"], row["asset_b"]) for _, row in candidates_df.iterrows()
        ]
        print(f"    [Funnel 1] Pares preseleccionados por SSD: {len(candidate_pairs)} de {total_combinations}")

        # Paso 2: Validación Econométrica Rigurosa (p-val <= 0.05, FDR <= 0.05, HL <= 30)
        validated_df = validator.validate_candidate_pairs(df_formation, candidate_pairs)

        if not validated_df.empty:
            merged_candidates = validated_df.merge(
                candidates_df[["asset_a", "asset_b", "ssd", "correlation"]],
                on=["asset_a", "asset_b"],
                how="left"
            )
        else:
            merged_candidates = pd.DataFrame()

        approved_pairs = validated_df[validated_df["is_valid_pair"]] if not validated_df.empty else pd.DataFrame()
        n_approved = len(approved_pairs)
        print(f"    [Funnel 2] Pares validados (Cointegración + Half-Life <= 30d + FDR=0.05): {n_approved}")

        # Registrar candidatos evaluados en esta ventana
        if not merged_candidates.empty:
            for _, cand_row in merged_candidates.iterrows():
                pair_key = f"{cand_row['asset_a']}_{cand_row['asset_b']}"
                rej_reasons = []
                if not cand_row["is_cointegrated"]:
                    rej_reasons.append(f"p-val={cand_row['p_value']:.4f}>0.05")
                if not cand_row["is_half_life_valid"]:
                    rej_reasons.append(f"HL={cand_row['half_life']:.1f}d no en [{validator.min_half_life}, {validator.max_half_life}]")
                if not cand_row["fdr_approved"]:
                    rej_reasons.append("Rechazado por FDR Benjamini-Hochberg (alpha=0.05)")

                status_str = "APROBADO" if cand_row["is_valid_pair"] else "RECHAZADO (" + ", ".join(rej_reasons) + ")"

                all_candidates_audit.append({
                    "window": w_idx + 1,
                    "formation_period": f"{f_start} a {f_end}",
                    "trading_period": f"{t_start} a {t_end}",
                    "pair": pair_key,
                    "correlation": round(float(cand_row.get("correlation", 0.0)), 4),
                    "ssd": round(float(cand_row.get("ssd", 0.0)), 2),
                    "coint_stat": round(float(cand_row["coint_stat"]), 4),
                    "p_value": round(float(cand_row["p_value"]), 4),
                    "half_life": round(float(cand_row["half_life"]), 2) if not np.isinf(cand_row["half_life"]) else None,
                    "is_cointegrated": bool(cand_row["is_cointegrated"]),
                    "is_half_life_valid": bool(cand_row["is_half_life_valid"]),
                    "fdr_approved": bool(cand_row["fdr_approved"]),
                    "is_valid_pair": bool(cand_row["is_valid_pair"]),
                    "status": status_str
                })

        if not merged_candidates.empty:
            print("    [Auditoría Candidatos Top IS]:")
            for _, c_row in merged_candidates.head(4).iterrows():
                p_label = f"{c_row['asset_a']}/{c_row['asset_b']}"
                p_val_lbl = f"{c_row['p_value']:.4f}"
                hl_lbl = f"{c_row['half_life']:.1f}d" if not np.isinf(c_row['half_life']) else "inf"
                corr_lbl = f"{c_row.get('correlation', 0.0):.2f}"
                stat_lbl = "APROBADO" if c_row["is_valid_pair"] else "RECHAZADO"
                print(f"      - {p_label:<10} | Corr: {corr_lbl:>5} | p-val: {p_val_lbl:>6} | HL: {hl_lbl:>6} -> {stat_lbl}")

        w_record = {
            "window": w_idx + 1,
            "formation_start": f_start,
            "formation_end": f_end,
            "trading_start": t_start,
            "trading_end": t_end,
            "ssd_candidates": len(candidate_pairs),
            "validated_pairs": n_approved,
            "trades": []
        }

        if approved_pairs.empty:
            print("    [Info] Ningún par superó los criterios econométricos en esta ventana. No se opera.")
        else:
            for _, pair_row in approved_pairs.iterrows():
                a = pair_row["asset_a"]
                b = pair_row["asset_b"]
                hl = pair_row["half_life"]
                coint_p = pair_row["p_value"]

                p_a_oos = df_trading[a]
                p_b_oos = df_trading[b]

                # Filtro de Kalman secuencial con detección de ruptura
                kalman = KalmanSpreadTracker(breakdown_threshold=5.0)
                kalman_df = kalman.filter_series(p_a_oos, p_b_oos)

                # Z-Score y volatilidad condicional GARCH/EWMA
                z_score = signal_gen.compute_zscore(kalman_df["spread"], rolling_window=min(30, len(kalman_df)))
                cond_vol = signal_gen.garch_estimator.estimate_volatility(kalman_df["spread"])

                # Correlación móvil
                ret_a = p_a_oos.pct_change()
                ret_b = p_b_oos.pct_change()
                roll_corr = ret_a.rolling(20, min_periods=5).corr(ret_b).fillna(1.0)

                # Generación de Señales adaptativas con flag de ruptura Kalman
                signals_df = signal_gen.generate_signals(
                    spread=kalman_df["spread"],
                    z_score=z_score,
                    half_life=hl,
                    rolling_correlation=roll_corr,
                    conditional_vol=cond_vol,
                    kalman_breakdown=kalman_df["is_broken"]
                )

                # Simulación de trading OOS con RiskManager (Hard Stop-Loss -8%)
                history_df, trades_df = backtester.simulate_pair(
                    prices_a=p_a_oos,
                    prices_b=p_b_oos,
                    signals=signals_df["position"],
                    hedge_ratio=kalman_df["beta"],
                    signals_exit_reasons=signals_df["exit_reason"]
                )

                # Evaluación de Métricas con PerformanceEvaluator
                metrics = PerformanceEvaluator.calculate_metrics(
                    equity_curve=history_df["net_equity"],
                    gross_equity_curve=history_df["gross_equity"],
                    trades_df=trades_df
                )

                pair_name = f"{a}_{b}"
                n_trades = len(trades_df)
                ret_net = metrics.get("total_net_return", 0.0)
                sharpe = metrics.get("sharpe_ratio", 0.0)
                max_dd = metrics.get("max_drawdown", 0.0)
                win_rate = metrics.get("win_rate", 0.0)
                p_factor = metrics.get("profit_factor", 0.0)

                print(f"      * Par: {pair_name:<10} | p-val: {coint_p:.4f} | HL: {hl:.1f}d | Trades: {n_trades} | Ret Neto: {ret_net:>7.2%} | Sharpe: {sharpe:>5.2f} | MaxDD: {max_dd:>7.2%}")

                # Log de trades individuales y acumulación para auditoría
                if not trades_df.empty:
                    for _, tr in trades_df.iterrows():
                        d_in = str(tr["entry_date"])[:10]
                        d_out = str(tr["exit_date"])[:10]
                        dr = tr["direction"]
                        pnl = float(tr.get("pnl_net", 0.0))
                        ret_p = float(tr.get("return_pct", 0.0))
                        reason = tr.get("exit_reason", "none")
                        print(f"        -> Trade: {dr} | {d_in} a {d_out} | PnL: ${pnl:>9.2f} ({ret_p:>6.2%}) | Salida: {reason}")

                        all_trades_records.append({
                            "window": w_idx + 1,
                            "pair": pair_name,
                            "direction": dr,
                            "entry_date": d_in,
                            "exit_date": d_out,
                            "entry_price_a": tr.get("entry_price_a"),
                            "entry_price_b": tr.get("entry_price_b"),
                            "exit_price_a": tr.get("exit_price_a"),
                            "exit_price_b": tr.get("exit_price_b"),
                            "shares_a": tr.get("shares_a"),
                            "shares_b": tr.get("shares_b"),
                            "initial_notional": tr.get("initial_notional"),
                            "pnl_net": pnl,
                            "return_pct": ret_p,
                            "exit_reason": reason
                        })

                summary_records.append({
                    "window": w_idx + 1,
                    "pair": pair_name,
                    "coint_pvalue": coint_p,
                    "half_life": hl,
                    "trades": n_trades,
                    "net_return": ret_net,
                    "gross_return": metrics.get("total_gross_return", 0.0),
                    "friction_drag": metrics.get("friction_drag", 0.0),
                    "sharpe": sharpe,
                    "max_drawdown": max_dd,
                    "win_rate": win_rate,
                    "profit_factor": p_factor,
                    "expectancy": metrics.get("expectancy_per_trade", 0.0)
                })

        window_logs.append(w_record)

    # 5. Exportación y Resumen Consolidado
    print("\n[4/5] Exportando resultados consolidados de Experimento B...")
    output_csv = "results/walk_forward_exp_B_semis.csv"
    output_json = "results/walk_forward_exp_B_semis.json"
    audit_csv = "results/exp_B_candidates_audit.csv"
    trades_csv = "results/trades_exp_B_semis.csv"

    if all_candidates_audit:
        pd.DataFrame(all_candidates_audit).to_csv(audit_csv, index=False)
        print(f"      Auditoría de candidatos guardada en: {audit_csv} ({len(all_candidates_audit)} pares evaluados)")

    if summary_records:
        df_summary = pd.DataFrame(summary_records)
        df_summary.to_csv(output_csv, index=False)
        print(f"      Archivo CSV de ventanas generado: {output_csv}")
    else:
        print("      No se generaron registros de ventanas operadas.")
        pd.DataFrame().to_csv(output_csv, index=False)

    if all_trades_records:
        df_trades_all = pd.DataFrame(all_trades_records)
        df_trades_all.to_csv(trades_csv, index=False)
        print(f"      Registro de operaciones detalladas guardado en: {trades_csv} ({len(df_trades_all)} trades)")
    else:
        print("      No se ejecutaron operaciones en las ventanas OOS.")
        pd.DataFrame().to_csv(trades_csv, index=False)

    with open(output_json, "w") as f:
        json.dump(window_logs, f, indent=2)
    print(f"      Archivo JSON detallado: {output_json}")

    print("\n[5/5] Resumen Global del Experimento B (Semiconductores):")
    if summary_records:
        df_sum = pd.DataFrame(summary_records)
        total_trades = df_sum["trades"].sum()
        avg_sharpe = df_sum["sharpe"].mean()
        avg_ret = df_sum["net_return"].mean()
        max_dd_overall = df_sum["max_drawdown"].min()
        print(f"      Total operaciones ejecutadas OOS : {total_trades}")
        print(f"      Retorno Neto promedio por ventana: {avg_ret:.2%}")
        print(f"      Sharpe promedio OOS              : {avg_sharpe:.2f}")
        print(f"      Peor Drawdown registrado         : {max_dd_overall:.2%}")

    if all_trades_records:
        df_tr = pd.DataFrame(all_trades_records)
        print("\n      Distribución de Motivos de Salida (exit_reason):")
        for reason, count in df_tr["exit_reason"].value_counts().items():
            print(f"        - {reason:<22}: {count:>3} trades ({count / len(df_tr):.1%})")

    print("\n" + "=" * 78)
    print("EXPERIMENTO B FINALIZADO CON ÉXITO")
    print("=" * 78)


if __name__ == "__main__":
    main()
