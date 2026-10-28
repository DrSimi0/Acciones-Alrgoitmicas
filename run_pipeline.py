"""
Script ejecutable para correr la simulación Walk-Forward completa (run_pipeline.py).
Genera universo de prueba, ejecuta el embudo (SSD -> Cointegración -> OU -> FDR -> Kalman -> Backtest)
y exporta los reportes a results/.
"""

import os
import json
import pandas as pd
import numpy as np

from src.data import SyntheticMarketDataGenerator
from src.pipeline import PairsTradingPipeline


def main():
    print("=" * 70)
    print("INICIANDO SIMULACIÓN WALK-FORWARD DE PAIRS TRADING (SISTEMA MODULAR)")
    print("=" * 70)

    os.makedirs("results", exist_ok=True)

    # 1. Generación de Universo Sintético Controlado (600 barras diarias)
    # Incluye:
    # - Par 1 Cointegrado: PAIR_A1 y PAIR_A2 (beta=1.5, kappa=0.15)
    # - Par 2 Cointegrado: PAIR_B1 y PAIR_B2 (beta=0.8, kappa=0.20)
    # - 6 Acciones de Paseo Aleatorio Puro no cointegradas
    print("\n[1/4] Generando universo de prueba point-in-time (10 activos, 600 barras)...")
    y1, x1 = SyntheticMarketDataGenerator.generate_cointegrated_pair(n_bars=600, beta=1.5, ou_kappa=0.15, seed=10)
    y2, x2 = SyntheticMarketDataGenerator.generate_cointegrated_pair(n_bars=600, beta=0.8, ou_kappa=0.20, seed=20)
    random_stocks = SyntheticMarketDataGenerator.generate_random_walks(n_assets=6, n_bars=600, seed=30)

    prices_df = pd.concat([
        pd.Series(y1, name="PAIR_A1"),
        pd.Series(x1, name="PAIR_A2"),
        pd.Series(y2, name="PAIR_B1"),
        pd.Series(x2, name="PAIR_B2"),
        random_stocks
    ], axis=1)

    print(f"Dimensiones del universo: {prices_df.shape[0]} barras x {prices_df.shape[1]} activos.")
    print(f"Total de pares combinatorios posibles: {int(prices_df.shape[1] * (prices_df.shape[1] - 1) / 2)}")

    # 2. Inicialización del Pipeline Cuantitativo
    print("\n[2/4] Inicializando Pipeline Cuantitativo...")
    pipeline = PairsTradingPipeline(
        top_n_ssd=10,
        coint_pvalue=0.05,
        min_half_life=2.0,
        max_half_life=40.0,
        fdr_alpha=0.05,
        base_entry_z=2.0,
        exit_z=0.5,
        elastic_garch=True,
        initial_capital=100_000.0,
        short_borrow_rate=0.02,
        commission_bps=1.5,
        bid_ask_bps=3.0
    )

    # 3. Ejecución Walk-Forward (Formación: 252 barras, Trading OOS: 63 barras)
    print("\n[3/4] Ejecutando Walk-Forward (252 barras In-Sample / 63 barras Out-of-Sample)...")
    wf_results = pipeline.run_walk_forward(
        prices_df=prices_df,
        formation_bars=252,
        trading_bars=63,
        step_bars=63
    )

    print(f"\nVentanas Walk-Forward procesadas: {wf_results['num_windows']}")
    summary_records = []

    for w in wf_results["windows"]:
        print(f"\n--- Ventana {w['window']} ---")
        print(f"  Formación: {w['formation_start'].strftime('%Y-%m-%d')} a {w['formation_end'].strftime('%Y-%m-%d')}")
        print(f"  Negociación (OOS): {w['trading_start'].strftime('%Y-%m-%d')} a {w['trading_end'].strftime('%Y-%m-%d')}")
        print(f"  Candidatos preseleccionados por SSD: {w['candidates_ssd_count']}")
        print(f"  Pares validados (Cointegración + OU + FDR): {w['validated_pairs_count']}")

        for trade_info in w["traded_pairs"]:
            pair_name = trade_info["pair"]
            m = trade_info["metrics"]
            trades = trade_info["num_trades"]
            print(f"    * Operado: {pair_name} | Trades: {trades} | Retorno Neto: {m.get('total_net_return', 0):.2%} | Sharpe: {m.get('sharpe_ratio', 0):.2f} | Max DD: {m.get('max_drawdown', 0):.2%}")

            summary_records.append({
                "window": w["window"],
                "pair": pair_name,
                "trades": trades,
                "net_return": m.get("total_net_return", 0),
                "gross_return": m.get("total_gross_return", 0),
                "friction_drag": m.get("friction_drag", 0),
                "sharpe": m.get("sharpe_ratio", 0),
                "max_drawdown": m.get("max_drawdown", 0),
                "win_rate": m.get("win_rate", 0),
                "profit_factor": m.get("profit_factor", 0)
            })

    # 4. Exportación de Resultados
    print("\n[4/4] Exportando reportes a results/walk_forward_summary.csv...")
    if summary_records:
        df_summary = pd.DataFrame(summary_records)
        df_summary.to_csv("results/walk_forward_summary.csv", index=False)
        print("Reporte CSV guardado exitosamente.")
    else:
        print("No se registraron pares validados que generaran operaciones.")

    with open("results/walk_forward_raw.json", "w") as f:
        # Serialización de fechas
        json.dump(wf_results, f, default=str, indent=2)
    print("Reporte JSON detallado guardado.")
    print("\n" + "=" * 70)
    print("SIMULACIÓN WALK-FORWARD FINALIZADA CON ÉXITO")
    print("=" * 70)


if __name__ == "__main__":
    main()
