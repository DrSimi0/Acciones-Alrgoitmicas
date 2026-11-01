import glob
import json
import os
import numpy as np
import pandas as pd

def analyze_dataset(name, path):
    print("=" * 70)
    print(f"ANÁLISIS DE TRADES: {name}")
    print(f"Archivo: {path}")
    print("=" * 70)
    
    if not os.path.exists(path):
        print("El archivo no existe.")
        return None
        
    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"Error al leer: {e}")
        return None
        
    if df.empty:
        print("0 trades registrados (Dataframe vacío).")
        return None

    # Holding time
    if "entry_date" in df.columns and "exit_date" in df.columns:
        df["entry_dt"] = pd.to_datetime(df["entry_date"])
        df["exit_dt"] = pd.to_datetime(df["exit_date"])
        df["holding_days"] = (df["exit_dt"] - df["entry_dt"]).dt.days
        print(f"Duración de Operaciones (días):")
        print(f"  Media : {df['holding_days'].mean():.1f} días")
        print(f"  Mediana: {df['holding_days'].median():.1f} días")
        print(f"  Mín   : {df['holding_days'].min()} días")
        print(f"  Máx   : {df['holding_days'].max()} días")

    ret_col = "return_pct" if "return_pct" in df.columns else None
    pnl_col = "pnl_net" if "pnl_net" in df.columns else None

    if ret_col:
        wins = df[df[ret_col] > 0]
        losses = df[df[ret_col] < 0]
        ties = df[df[ret_col] == 0]
        win_rate = len(wins) / len(df)
        print(f"\nDesempeño Estadístico:")
        print(f"  Total Trades : {len(df)}")
        print(f"  Win Rate     : {win_rate:.1%} ({len(wins)} ganadores, {len(losses)} perdedores, {len(ties)} planos)")
        print(f"  Retorno Acum : {df[ret_col].sum():.2%}")
        print(f"  Retorno Medio: {df[ret_col].mean():.2%}")
        print(f"  Desv. Est.   : {df[ret_col].std():.2%}")

        gross_profit = wins[ret_col].sum() if len(wins) > 0 else 0.0
        gross_loss = abs(losses[ret_col].sum()) if len(losses) > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else np.nan
        print(f"  Profit Factor: {profit_factor:.2f}")

        avg_win = wins[ret_col].mean() if len(wins) > 0 else 0.0
        avg_loss = losses[ret_col].mean() if len(losses) > 0 else 0.0
        payoff_ratio = (avg_win / abs(avg_loss)) if abs(avg_loss) > 0 else np.nan
        print(f"  Ganancia Media: {avg_win:.2%}")
        print(f"  Pérdida Media : {avg_loss:.2%}")
        print(f"  Payoff Ratio  : {payoff_ratio:.2f}")
        print(f"  Mejor Trade   : {df[ret_col].max():.2%}")
        print(f"  Peor Trade    : {df[ret_col].min():.2%}")

    if pnl_col:
        print(f"\nPnL Neto Monetario ($):")
        print(f"  PnL Total  : ${df[pnl_col].sum():,.2f}")
        print(f"  PnL Medio  : ${df[pnl_col].mean():,.2f}")
        print(f"  PnL Mediana: ${df[pnl_col].median():,.2f}")

    # Costos de Fricción
    comm_total = df["commissions"].sum() if "commissions" in df.columns else 0.0
    borrow_total = df["borrow_fees"].sum() if "borrow_fees" in df.columns else 0.0
    print(f"\nCostos de Fricción Acumulados:")
    print(f"  Comisiones de corretaje: ${comm_total:,.2f}")
    print(f"  Short-Borrow Fees      : ${borrow_total:,.2f}")
    print(f"  Impacto Total Fricción : ${comm_total + borrow_total:,.2f}")

    # Desglose por patas
    if "pnl_leg_a" in df.columns and "pnl_leg_b" in df.columns:
        print(f"\nPnL por Pata:")
        print(f"  Pata A: ${df['pnl_leg_a'].sum():,.2f}")
        print(f"  Pata B: ${df['pnl_leg_b'].sum():,.2f}")
    elif "pnl_leg_asset" in df.columns and "pnl_leg_proxy" in df.columns:
        print(f"\nPnL por Pata (PCA Sintético):")
        print(f"  Pata Activo Idiosincrásico : ${df['pnl_leg_asset'].sum():,.2f}")
        print(f"  Pata Cobertura Proxy (SPY) : ${df['pnl_leg_proxy'].sum():,.2f}")

    # Exit reasons
    if "exit_reason" in df.columns:
        print("\nDesglose por Motivo de Salida (Exit Reason):")
        for r, c in df["exit_reason"].value_counts().items():
            sub = df[df["exit_reason"] == r]
            avg_r = sub[ret_col].mean() if ret_col else 0.0
            sum_pnl = sub[pnl_col].sum() if pnl_col else 0.0
            print(f"  - {r:<25}: {c:>2} trades ({c/len(df):>5.1%}) | Ret Medio: {avg_r:>6.2%} | PnL: ${sum_pnl:>8.2f}")

    # Directions
    if "direction" in df.columns:
        print("\nDesglose por Dirección:")
        for d, c in df["direction"].value_counts().items():
            sub = df[df["direction"] == d]
            avg_r = sub[ret_col].mean() if ret_col else 0.0
            sum_pnl = sub[pnl_col].sum() if pnl_col else 0.0
            print(f"  - {d:<15}: {c:>2} trades ({c/len(df):>5.1%}) | Ret Medio: {avg_r:>6.2%} | PnL: ${sum_pnl:>8.2f}")

    # Top Assets / Pairs
    id_col = "pair" if "pair" in df.columns else ("asset" if "asset" in df.columns else None)
    if id_col:
        print(f"\nDetalle por {id_col.upper()}:")
        grouped = df.groupby(id_col).agg(
            trades=("direction", "count"),
            win_rate=(ret_col, lambda s: (s > 0).mean()),
            ret_total=(ret_col, "sum"),
            ret_mean=(ret_col, "mean"),
            pnl_total=(pnl_col, "sum") if pnl_col else ("direction", "count")
        )
        print(grouped.to_string())

    print("\nLista detallada de trades:")
    cols_to_show = [c for c in ["entry_date", "exit_date", id_col, "direction", "exit_reason", ret_col, pnl_col, "borrow_fees"] if c in df.columns]
    print(df[cols_to_show].to_string())
    print("\n")
    return df

if __name__ == "__main__":
    analyze_dataset("Pares Fijos Fundamentales (Long/Short 50/50)", "results/trades_fixed_pairs_LS.csv")
    analyze_dataset("PCA S&P 100 Base (80% var, max HL 30d, exit_z 0.0)", "results/trades_pca_sp100_LS.csv")
    analyze_dataset("PCA S&P 100 Optimizado (87% var, max HL 12d, exit_z 0.75)", "results/trades_pca_sp100_optimized.csv")
    analyze_dataset("PCA S&P 100 Híbrido 'The Sweet Spot' (80% var, max HL 12d, exit_z 0.75)", "results/trades_pca_sp100_hybrid.csv")
    analyze_dataset("Semiconductores (Exp B Semis / Real Universe)", "results/trades_real_universe.csv")
