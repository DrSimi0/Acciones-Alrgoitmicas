"""
Script Central Coordinador — Pipeline de Producción (run_pipeline.py).

Evolución Cuantitativa: Arbitraje Estadístico Multivariado por Análisis de Componentes
Principales (PCA - Avellaneda & Lee, 2010) sobre el universo del S&P 100 (OEX).

Flujo Arquitectónico:
1. Ingesta Sincronizada S&P 100 (100 activos líderes + ETF proxy SPY).
2. Filtro Dinámico de Liquidez en Ventana In-Sample (ADTV 20 días >= $50M, Precio >= $10).
3. Extracción de Factores Sistemáticos (PCAFactorModel con umbral dinámico de varianza 80%).
4. Rigor Econométrico sobre Spreads Residuales (ADF p <= 0.05, Half-Life OU <= 30d, FDR Benjamini-Hochberg alpha = 0.05).
5. Ejecución Market-Neutral Long/Short Sintética:
   - Posición 100% nocional en activo subyacente.
   - Cobertura con ETF proxy (SPY) escalado por sum(beta_ik).
   - Control de Cuarentena Corporativa (Earnings Blackout) y Hard Stop-Loss (-8%).
   - Deducción diaria de borrow fees en patas cortas y costos bidireccionales completos.
6. Exportación de auditoría completa a results/walk_forward_pca_sp100_LS.csv y .json.
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
from src.pca_model import PCAFactorModel
from src.spread import EconometricValidator, KalmanSpreadTracker
from src.signals import SignalGenerator
from src.backtest import WalkForwardBacktester, MarketImpactModel, RiskManager, CorporateCalendarManager
from src.metrics import PerformanceEvaluator


# Lista oficial de componentes del S&P 100 (OEX)
SP100_TICKERS = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AIG", "AMD", "AMGN", "AMZN", "AVGO",
    "AXP", "BA", "BAC", "BK", "BKNG", "BLK", "BMY", "C", "CAT", "CHTR",
    "CL", "CMCSA", "COF", "COP", "COST", "CRM", "CSCO", "CVS", "CVX", "DHR",
    "DIS", "DOW", "DUK", "EMR", "EXC", "F", "FDX", "GD", "GE", "GILD",
    "GM", "GOOG", "GOOGL", "GS", "HD", "HON", "IBM", "INTC", "INTU", "ISRG",
    "JNJ", "JPM", "KHC", "KO", "LIN", "LLY", "LMT", "LOW", "MA", "MCD",
    "MDLZ", "MDT", "MET", "META", "MMM", "MO", "MRK", "MS", "MSFT", "NEE",
    "NFLX", "NKE", "NVDA", "ORCL", "PEP", "PFE", "PG", "PM", "PYPL", "QCOM",
    "RTX", "SBUX", "SCHW", "SO", "SPG", "T", "TGT", "TMO", "TMUS", "TXN",
    "UNH", "UNP", "UPS", "USB", "V", "VZ", "WFC", "WMT", "XOM"
]

ETF_PROXY = "SPY"


def run_trading_pipeline(
    start_date: str = "2021-01-01",
    end_date: str = "2025-12-31",
    min_adtv: float = 50_000_000.0,
    min_price: float = 10.0,
    variance_threshold: float = 0.87,
    coint_pvalue_threshold: float = 0.05,
    max_half_life: float = 12.0,
    exit_z: float = 0.75,
    fdr_alpha: float = 0.05
) -> None:
    """
    Pipeline de Producción Multivariado PCA con Ejecución Sintética Market-Neutral (Long/Short vs SPY).
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.info("Iniciando Pipeline de Producción PCA — S&P 100 Market-Neutral (100 activos + SPY)")

    print("=" * 82)
    print("SISTEMA CUANTITATIVO DE STAT ARB — PIPELINE PCA S&P 100 (AVELLANEDA & LEE)")
    print("=" * 82)

    os.makedirs("results", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    prices_cache_path = os.path.join("data", "sp100_prices.csv")
    volumes_cache_path = os.path.join("data", "sp100_volumes.csv")

    all_universe_tickers = sorted(list(set(SP100_TICKERS + [ETF_PROXY])))

    print(f"\n[1/5] Ingesta de Mercado: S&P 100 ({len(SP100_TICKERS)} activos) + Proxy ({ETF_PROXY})...")
    print(f"      Periodo: {start_date} a {end_date}")

    # Cargar de caché local si existe para acelerar ejecuciones
    if os.path.exists(prices_cache_path) and os.path.exists(volumes_cache_path):
        print("      Cargando historial desde caché local persistente (data/)...")
        prices_df = pd.read_csv(prices_cache_path, index_col=0, parse_dates=True)
        volumes_df = pd.read_csv(volumes_cache_path, index_col=0, parse_dates=True)
    else:
        print("      Descargando precios y volúmenes vía Yahoo Finance...")
        prices_df, volumes_df = EquityDataLoader.load_historical_market_data(
            tickers=all_universe_tickers,
            start_date=start_date,
            end_date=end_date
        )
        prices_df.to_csv(prices_cache_path)
        volumes_df.to_csv(volumes_cache_path)
        print("      Datos de mercado guardados en caché local.")

    n_bars, n_total_assets = prices_df.shape
    print(f"      Base de datos sincronizada: {n_bars} barras diarias para {n_total_assets} activos.")

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

    # 3. Inicialización de Motores Cuantitativos
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

    # Gestor de calendario corporativo sintético para todo el universo
    calendar_manager = CorporateCalendarManager.generate_synthetic_schedule(
        tickers=all_universe_tickers,
        start_date=start_date,
        end_date=end_date
    )

    backtester = WalkForwardBacktester(
        initial_capital=100_000.0,
        max_leverage=1.0,
        impact_model=impact_model,
        risk_manager=risk_manager,
        calendar_manager=calendar_manager,
        capital_allocation_mode="synthetic_pca"
    )

    print("\n[3/5] Ejecutando Simulación Walk-Forward Multivariada PCA:")
    print(f"      - Filtro de Liquidez In-Sample: ADTV >= ${min_adtv:,.0f} | Precio >= ${min_price:.2f}")
    print(f"      - Umbral de Varianza Explicada PCA: {variance_threshold:.0%}")
    print(f"      - Validación Econométrica: ADF p <= {coint_pvalue_threshold}, Half-Life <= {max_half_life:.0f}d, FDR = {fdr_alpha:.2f}")
    print(f"      - Ejecución: Long/Short Sintética (Activo vs Beta-Proxy SPY) con Costo de Préstamo (2% anual)")

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

        # In-sample data para activos individuales (excluyendo SPY del fit PCA)
        available_stocks = [t for t in SP100_TICKERS if t in formation_df.columns]
        is_stock_prices = formation_df[available_stocks]
        is_stock_volumes = volumes_df.loc[formation_df.index, available_stocks]

        # Filtro de liquidez dinámico in-sample
        liquid_assets = EquityDataLoader.filter_by_liquidity(
            prices_df=is_stock_prices,
            volumes_df=is_stock_volumes,
            min_adtv=min_adtv,
            min_price=min_price,
            window=20
        )
        pct_liquid = (len(liquid_assets) / len(available_stocks)) if available_stocks else 0.0
        print(f"    [Liquidez] {len(liquid_assets)}/{len(available_stocks)} activos líquidos ({pct_liquid:.1%})")

        if len(liquid_assets) < 10:
            print("    [!] Advertencia: Menos de 10 activos superaron el filtro de liquidez. Ventana omitida.")
            continue

        # Retornos del periodo de formación
        is_returns = is_stock_prices[liquid_assets].pct_change().dropna()
        if len(is_returns) < 50:
            print("    [!] Advertencia: Historial de retornos insuficiente. Ventana omitida.")
            continue

        # Ajuste del Modelo PCA
        pca = PCAFactorModel(variance_threshold=variance_threshold, use_svd=True)
        try:
            pca.fit(is_returns)
        except Exception as e:
            print(f"    [!] Error en ajuste PCA: {e}. Ventana omitida.")
            continue

        k_comp = pca.n_components_
        cum_var = float(pca.cumulative_variance_ratio_[-1]) if pca.cumulative_variance_ratio_ is not None else 0.0
        print(f"    [PCA] {k_comp} factores extraídos | Varianza explicada: {cum_var:.2%}")

        # Extracción y validación econométrica de residuales sintéticos
        residuals_is = pca.get_idiosyncratic_residuals()
        audit_df = validator.validate_pca_residuals(residuals_is)

        if audit_df.empty:
            print("    [Econometría] No se pudieron calcular diagnósticos sobre residuales.")
            continue

        audit_df["window_id"] = window_idx
        for _, row in audit_df.iterrows():
            candidates_audit_records.append(row.to_dict())

        approved_df = audit_df[audit_df["is_valid_residual"] == True]
        approved_assets = list(approved_df["asset"].values)
        print(f"    [Econometría] {len(approved_assets)}/{len(liquid_assets)} residuales aprobados (ADF + OU <= {max_half_life:.0f}d + FDR={fdr_alpha:.2f})")

        if not approved_assets:
            print("    [-] Sin activos aprobados para negociación en esta ventana OOS.")
            window_logs.append({
                "window": window_idx,
                "in_sample_range": [is_start, is_end],
                "out_of_sample_range": [oos_start, oos_end],
                "liquid_assets": len(liquid_assets),
                "k_components": k_comp,
                "variance_explained": cum_var,
                "approved_assets": 0,
                "trades_count": 0,
                "net_return": 0.0,
                "sharpe": 0.0,
                "max_drawdown": 0.0
            })
            continue

        # Proyección de retornos y residuales fuera de muestra (OOS)
        oos_stock_prices = trading_df[liquid_assets]
        oos_returns = oos_stock_prices.pct_change().dropna()

        residuals_oos = pca.get_idiosyncratic_residuals(oos_returns)

        # Simulación independiente por cada activo aprobado contra el proxy ETF (SPY)
        window_trades = []
        window_pnl_list = []
        window_metrics_list = []

        spy_prices_oos = trading_df[ETF_PROXY]
        spy_ret_oos = spy_prices_oos.pct_change().fillna(0.0)

        for asset in approved_assets:
            if asset not in trading_df.columns:
                continue

            stock_prices_oos = trading_df[asset]
            stock_ret_oos = stock_prices_oos.pct_change().fillna(0.0)

            # Suma de cargas factoriales: beta_total = sum(beta_ik)
            loadings_series = pca.factor_loadings_.loc[asset]
            beta_total = float(loadings_series.sum())
            beta_effective = max(abs(beta_total), 0.1)

            # Serie residual acumulada continua para evitar sesgos de calentamiento en Z-score
            is_tail = residuals_is[asset].iloc[-60:]
            shift_val = is_tail.iloc[-1]
            continuous_spread = pd.concat([is_tail, residuals_oos[asset] + shift_val])
            full_zscore = signal_gen.compute_zscore(continuous_spread, rolling_window=60)
            oos_zscore = full_zscore.reindex(trading_df.index).fillna(0.0)

            oos_spread = residuals_oos[asset].reindex(trading_df.index).ffill().bfill()

            # Correlación móvil contemporánea con SPY
            rolling_corr = stock_ret_oos.rolling(20, min_periods=5).corr(spy_ret_oos).bfill().fillna(0.5)

            # Volatilidad condicional estimada vía GARCH/EWMA
            cond_vol = signal_gen.garch_estimator.estimate_volatility(oos_spread.diff().dropna())

            # Half-life estimada in-sample
            hl_asset = float(approved_df.loc[approved_df["asset"] == asset, "half_life"].values[0])

            # Generación de señales de trading
            signals_df = signal_gen.generate_signals(
                spread=oos_spread,
                z_score=oos_zscore,
                half_life=hl_asset,
                rolling_correlation=rolling_corr,
                conditional_vol=cond_vol
            )
            positions = signals_df["position"]

            # Ejecución en WalkForwardBacktester
            beta_series = pd.Series(beta_effective, index=trading_df.index)
            hist_df, trades_df = backtester.simulate_pair(
                prices_a=stock_prices_oos,
                prices_b=spy_prices_oos,
                signals=positions,
                hedge_ratio=beta_series,
                signals_exit_reasons=signals_df["exit_reason"],
                ticker_a=asset,
                ticker_b=ETF_PROXY
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
                    trade_dict["asset"] = asset
                    trade_dict["proxy"] = ETF_PROXY
                    trade_dict["beta_total"] = beta_total
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
            "liquid_assets": len(liquid_assets),
            "k_components": k_comp,
            "variance_explained": cum_var,
            "approved_assets": len(approved_assets),
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
            "approved_assets": len(approved_assets)
        })

    # 4. Exportación y Resumen Final
    print("\n[4/5] Guardando registros cuantitativos...")

    output_csv = "results/walk_forward_pca_sp100_optimized.csv"
    output_json = "results/walk_forward_pca_sp100_optimized.json"
    trades_csv = "results/trades_pca_sp100_optimized.csv"
    candidates_audit_csv = "results/pca_sp100_optimized_candidates_audit.csv"

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

    print("\n[5/5] Resumen Consolidado Global — Stat Arb PCA S&P 100:")
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
    print("PIPELINE PCA S&P 100 MARKET-NEUTRAL FINALIZADO CON ÉXITO")
    print("=" * 82)


def run_fixed_pairs_pipeline():
    """
    Pipeline Experimental: Pares Fijos Fundamentales con Ejecución Market-Neutral Long/Short Simétrica.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logging.info("Iniciando Pipeline de Pares Fijos Fundamentales — Modo Market-Neutral Long/Short (50/50)")

    print("=" * 78)
    print("SISTEMA CUANTITATIVO DE PAIRS TRADING — PARES FIJOS FUNDAMENTALES (LONG/SHORT)")
    print("=" * 78)

    os.makedirs("results", exist_ok=True)

    fixed_pairs = [
        ("KO", "PEP"),    # Bebidas / Consumo defensivo
        ("V", "MA"),      # Redes de pagos / Fintech
        ("CVX", "XOM"),   # Energía integrada / Petróleo
        ("HD", "LOW"),    # Retail de mejoras para el hogar
        ("UNP", "CSX")    # Transporte ferroviario
    ]
    unique_tickers = sorted(list(set([t for pair in fixed_pairs for t in pair])))
    start_date = "2021-01-01"
    end_date = "2025-12-31"

    print(f"\n[1/5] Descargando precios reales vía yfinance ({len(unique_tickers)} activos, {len(fixed_pairs)} pares fijos)...")
    prices_df = EquityDataLoader.load_historical_prices(
        tickers=unique_tickers,
        start_date=start_date,
        end_date=end_date
    )

    formation_bars = 252
    trading_bars = 63
    step_bars = 63

    splits = WalkForwardSplitter.split(
        data=prices_df,
        formation_bars=formation_bars,
        trading_bars=trading_bars,
        step_bars=step_bars
    )

    validator = EconometricValidator(
        coint_pvalue_threshold=0.05,
        min_half_life=2.0,
        max_half_life=30.0,
        fdr_alpha=0.05
    )
    signal_gen = SignalGenerator(base_entry_z=2.0, exit_z=0.5, elastic_volatility=True)
    impact_model = MarketImpactModel(
        commission_bps=1.5,
        bid_ask_spread_bps=3.0,
        impact_parameter=0.05,
        short_borrow_rate_annual=0.02
    )
    risk_manager = RiskManager(max_loss_pct=-0.08)
    calendar_manager = CorporateCalendarManager.generate_synthetic_schedule(
        tickers=unique_tickers,
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

    all_trades_records: List[Dict[str, Any]] = []
    window_logs: List[Dict[str, Any]] = []
    summary_records: List[Dict[str, Any]] = []
    candidates_audit_records: List[Dict[str, Any]] = []

    for window_idx, (formation_df, trading_df) in enumerate(splits, start=1):
        is_start = formation_df.index[0].strftime("%Y-%m-%d")
        is_end = formation_df.index[-1].strftime("%Y-%m-%d")
        oos_start = trading_df.index[0].strftime("%Y-%m-%d")
        oos_end = trading_df.index[-1].strftime("%Y-%m-%d")

        audit_df = validator.validate_candidate_pairs(
            candidate_pairs=fixed_pairs,
            prices_df=formation_df
        )
        audit_df["window_id"] = window_idx
        for _, row in audit_df.iterrows():
            candidates_audit_records.append(row.to_dict())

        valid_pairs_df = audit_df[audit_df["is_valid_pair"] == True]
        valid_pairs = [tuple(p) for p in valid_pairs_df["pair"].values]

        window_trades = []
        window_pnl_list = []
        window_metrics_list = []

        for pair in valid_pairs:
            asset_a, asset_b = pair
            p_a_form = formation_df[asset_a]
            p_b_form = formation_df[asset_b]

            beta_tracker = KalmanSpreadTracker(delta=1e-4, vt_param=1e-3)
            beta_series_form, spread_series_form, error_var_form = beta_tracker.fit_transform(p_a_form, p_b_form)

            p_a_trade = trading_df[asset_a]
            p_b_trade = trading_df[asset_b]

            beta_trade, spread_trade, error_var_trade, breakdown_trade = beta_tracker.filter_online(
                p_a_trade, p_b_trade, freeze_beta=False
            )

            continuous_spread = pd.concat([spread_series_form.iloc[-60:], spread_trade])
            full_zscore = signal_gen.compute_zscore(continuous_spread, rolling_window=60)
            oos_zscore = full_zscore.loc[trading_df.index]

            rolling_corr = p_a_trade.pct_change().rolling(20).corr(p_b_trade.pct_change()).bfill().fillna(0.5)
            cond_vol = signal_gen.garch_estimator.estimate_volatility(spread_trade.diff().dropna())

            hl = float(valid_pairs_df.loc[valid_pairs_df["pair"] == pair, "half_life"].values[0])

            signals_df = signal_gen.generate_signals(
                spread=spread_trade,
                z_score=oos_zscore,
                half_life=hl,
                rolling_correlation=rolling_corr,
                conditional_vol=cond_vol,
                kalman_breakdown=breakdown_trade
            )
            positions = signals_df["position"]

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

        summary_records.append({
            "window": window_idx,
            "net_return": avg_ret,
            "sharpe": avg_sharpe,
            "max_drawdown": max_dd,
            "trades": len(window_trades),
            "cointegrated_pairs": len(valid_pairs)
        })

    output_csv = "results/walk_forward_fixed_pairs_LS.csv"
    trades_csv = "results/trades_fixed_pairs_LS.csv"
    output_json = "results/walk_forward_fixed_pairs_LS.json"

    if summary_records:
        pd.DataFrame(summary_records).to_csv(output_csv, index=False)
    if all_trades_records:
        pd.DataFrame(all_trades_records).to_csv(trades_csv, index=False)
    with open(output_json, "w") as f:
        json.dump(summary_records, f, indent=2)

    print("Pipeline de Pares Fijos finalizado.")


def main():
    """Punto de entrada principal: ejecuta por defecto el Pipeline Multivariado PCA S&P 100."""
    run_trading_pipeline()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--fixed-pairs", "-f", "fixed_pairs"):
        run_fixed_pairs_pipeline()
    else:
        main()
