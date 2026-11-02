"""
Módulo de Optimización de Apalancamiento y Criterio de Kelly (optimize_leverage.py).

Calcula el apalancamiento óptimo continuo (Full Kelly y Half-Kelly) frente a la tasa
de financiamiento de margen de Interactive Brokers (6.80% anual) para la estrategia
PCA Híbrida del S&P 100. Simula las trayectorias de capital resultantes a 1x, 2x, 3x
y Half-Kelly deduciendo los costos diarios de margen sobre el capital prestado.
"""

import os
import sys
import argparse
from typing import Dict, List, Tuple, Any, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


# Tasa de margen institucional de referencia (Interactive Brokers benchmark: 6.80% anual)
DEFAULT_ANNUAL_MARGIN_RATE = 0.068
TRADING_DAYS_PER_YEAR = 252


def load_strategy_daily_returns(
    trades_path: str = "results/trades_pca_sp100_10years.csv",
    prices_path: str = "data/sp100_prices_10y.csv",
    initial_capital: float = 100_000.0
) -> pd.Series:
    """
    Reconstruye la serie continua de retornos diarios Mark-to-Market (MTM) de la estrategia.

    Para cada posición activa entre entry_date y exit_date, calcula la variación de PnL
    diaria de la pata de la acción y la pata de cobertura (SPY). En los días sin posiciones
    activas (cartera en liquidez protegida por el filtro FDR), el retorno es 0.0.

    Args:
        trades_path: Ruta al archivo CSV de operaciones ejecutadas.
        prices_path: Ruta al archivo CSV con precios diarios de mercado.
        initial_capital: Capital base nominal de la simulación ($100,000).

    Returns:
        pd.Series con los retornos diarios R_t indexados por fecha.
    """
    if not os.path.exists(trades_path):
        raise FileNotFoundError(f"No se encontró el archivo de trades en: {trades_path}")
    if not os.path.exists(prices_path):
        raise FileNotFoundError(f"No se encontró el archivo de precios en: {prices_path}")

    trades_df = pd.read_csv(trades_path)
    if trades_df.empty:
        raise ValueError(f"El archivo de trades {trades_path} no contiene operaciones registradas.")

    prices_df = pd.read_csv(prices_path, index_col=0, parse_dates=True)

    start_date = pd.to_datetime(trades_df["entry_date"].min())
    end_date = pd.to_datetime(trades_df["exit_date"].max())
    all_dates = prices_df.loc[start_date:end_date].index

    daily_pnl = pd.Series(0.0, index=all_dates)

    for _, trade in trades_df.iterrows():
        asset = trade["asset"]
        entry = pd.to_datetime(trade["entry_date"])
        exit = pd.to_datetime(trade["exit_date"])
        shares_a = trade["shares_a"]
        shares_b = trade["shares_b"]
        pnl_net = trade["pnl_net"]

        sub_dates = prices_df.loc[entry:exit].index
        if len(sub_dates) < 2:
            # Operación intradiaria o de 0 días
            if entry in daily_pnl.index:
                daily_pnl.loc[entry] += pnl_net
            continue

        p_a = prices_df.loc[sub_dates, asset]
        p_b = prices_df.loc[sub_dates, "SPY"]

        # Variaciones diarias de precio
        diff_a = p_a.diff().fillna(0.0)
        diff_b = p_b.diff().fillna(0.0)

        # PnL por pata
        trade_daily_pnl = (shares_a * diff_a) + (shares_b * diff_b)

        # Ajuste proporcional exacto para igualar el pnl_net (fricciones y comisiones de salida)
        sum_daily = trade_daily_pnl.sum()
        scale = (pnl_net / sum_daily) if abs(sum_daily) > 1e-6 else 1.0
        adjusted_daily = trade_daily_pnl * scale

        for dt, pnl_val in adjusted_daily.items():
            if dt in daily_pnl.index:
                daily_pnl.loc[dt] += pnl_val

    # Retorno diario porcentual sobre el capital inicial
    daily_returns = daily_pnl / initial_capital
    return daily_returns


def calculate_kelly_criterion(
    daily_returns: pd.Series,
    annual_margin_rate: float = DEFAULT_ANNUAL_MARGIN_RATE
) -> Dict[str, Any]:
    """
    Calcula el Criterio de Kelly en tiempo continuo y sus métricas estocásticas.

    Fórmula:
        L* = (mu - r_f) / sigma^2
        Half-Kelly = L* / 2

    Args:
        daily_returns: Serie de retornos diarios de la estrategia.
        annual_margin_rate: Tasa de interés de margen anualizada (ej. 0.068).

    Returns:
        Diccionario con mu, sigma, sigma^2, r_f diario, Full Kelly y Half-Kelly.
    """
    rf_daily = annual_margin_rate / TRADING_DAYS_PER_YEAR
    mu_daily = float(daily_returns.mean())
    var_daily = float(daily_returns.var())
    std_daily = float(daily_returns.std())

    mu_annual = mu_daily * TRADING_DAYS_PER_YEAR
    vol_annual = std_daily * np.sqrt(TRADING_DAYS_PER_YEAR)

    if var_daily > 1e-12:
        full_kelly = (mu_daily - rf_daily) / var_daily
    else:
        full_kelly = 0.0

    half_kelly = full_kelly / 2.0

    return {
        "mu_daily": mu_daily,
        "std_daily": std_daily,
        "var_daily": var_daily,
        "mu_annual": mu_annual,
        "vol_annual": vol_annual,
        "rf_daily": rf_daily,
        "rf_annual": annual_margin_rate,
        "full_kelly": full_kelly,
        "half_kelly": half_kelly
    }


def simulate_leveraged_curves(
    daily_returns: pd.Series,
    leverage_levels: List[float],
    annual_margin_rate: float = DEFAULT_ANNUAL_MARGIN_RATE,
    initial_capital: float = 100_000.0
) -> Tuple[pd.DataFrame, pd.DataFrame, List[Dict[str, Any]]]:
    """
    Simula las curvas de capital para distintos múltiplos de apalancamiento,
    restando diariamente el costo del margen sobre la porción prestada (L - 1).

    Ecuación diaria:
        R_t(L) = L * R_t - (L - 1) * r_f_diario   (para L > 1)
        R_t(L) = L * R_t                         (para L <= 1)

    Args:
        daily_returns: Serie de retornos diarios base.
        leverage_levels: Lista de multiplicadores L a simular.
        annual_margin_rate: Tasa anual de costo de margen.
        initial_capital: Capital inicial en dólares.

    Returns:
        Tuple[DataFrame de curvas NAV, DataFrame de Drawdowns, Lista de métricas].
    """
    rf_daily = annual_margin_rate / TRADING_DAYS_PER_YEAR
    n_days = len(daily_returns)

    nav_dict = {}
    dd_dict = {}
    metrics_list = []

    for L in leverage_levels:
        label = f"L={L:.2f}x"
        if L > 1.0:
            borrow_cost = (L - 1.0) * rf_daily
            leveraged_ret = (L * daily_returns) - borrow_cost
        elif L > 0.0:
            leveraged_ret = L * daily_returns
        else:
            leveraged_ret = pd.Series(0.0, index=daily_returns.index)

        # Curva de capital acumulada
        growth_factor = 1.0 + leveraged_ret
        # Evitar valores negativos irreales por liquidación total
        growth_factor = np.maximum(growth_factor, 0.0)
        equity_series = initial_capital * growth_factor.cumprod()

        # Cálculo de Drawdowns
        peak = equity_series.cummax()
        drawdown_series = (equity_series - peak) / peak

        tot_return = float((equity_series.iloc[-1] / initial_capital) - 1.0)
        max_dd = float(drawdown_series.min())

        ann_vol = float(leveraged_ret.std() * np.sqrt(TRADING_DAYS_PER_YEAR))
        if tot_return > -1.0 and n_days > 0:
            cagr = float((1.0 + tot_return) ** (TRADING_DAYS_PER_YEAR / n_days) - 1.0)
        else:
            cagr = -1.0

        excess_cagr = cagr - annual_margin_rate
        sharpe = (excess_cagr / ann_vol) if ann_vol > 1e-6 else 0.0
        calmar = (abs(cagr) / abs(max_dd)) if abs(max_dd) > 1e-6 else 0.0

        nav_dict[label] = equity_series
        dd_dict[label] = drawdown_series

        metrics_list.append({
            "label": label,
            "leverage": L,
            "total_return": tot_return,
            "cagr": cagr,
            "annual_vol": ann_vol,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "calmar": calmar,
            "final_nav": float(equity_series.iloc[-1])
        })

    nav_df = pd.DataFrame(nav_dict, index=daily_returns.index)
    dd_df = pd.DataFrame(dd_dict, index=daily_returns.index)

    return nav_df, dd_df, metrics_list


def plot_leverage_simulation(
    nav_df: pd.DataFrame,
    dd_df: pd.DataFrame,
    period_label: str,
    output_png: str = "results/leverage_simulation.png"
) -> None:
    """
    Genera y guarda un gráfico institucional de dos paneles con matplotlib:
    Panel Superior: Curvas de NAV ($)
    Panel Inferior: Gráfico de Drawdowns submarinos (Underwater Chart)
    """
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [2.2, 1.2]})

    colors = ["#1f77b4", "#ff7f0e", "#d62728", "#2ca02c", "#9467bd"]

    for idx, col in enumerate(nav_df.columns):
        color = colors[idx % len(colors)]
        ax1.plot(nav_df.index, nav_df[col], label=col, linewidth=1.8, color=color)
        ax2.plot(dd_df.index, dd_df[col] * 100.0, label=col, linewidth=1.4, color=color)

    ax1.set_title(f"Simulación de Apalancamiento Dinámico (Criterio de Kelly) — PCA Híbrido ({period_label})", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Valor de Liquidación NAV ($)", fontsize=11)
    ax1.yaxis.set_major_formatter("${x:,.0f}")
    ax1.axhline(100_000, color="gray", linestyle="--", alpha=0.6, label="Capital Inicial ($100k)")
    ax1.legend(loc="upper left", frameon=True, fontsize=10)
    ax1.grid(True, linestyle=":", alpha=0.6)

    ax2.set_title("Inmersión de Drawdown (%)", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Drawdown (%)", fontsize=11)
    ax2.set_xlabel("Fecha", fontsize=11)
    ax2.yaxis.set_major_formatter("{x:.0f}%")
    ax2.axhline(0.0, color="black", linestyle="-", linewidth=0.8)
    ax2.axhline(-8.0, color="darkred", linestyle=":", label="Hard Stop-Loss (-8%)")
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="lower left", frameon=True, fontsize=9)

    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_png), exist_ok=True)
    plt.savefig(output_png, dpi=300)
    plt.close()
    print(f"\n[Visualización] Gráfico guardado exitosamente en: {output_png}")


def run_leverage_optimization(
    period: str = "10years",
    annual_margin_rate: float = DEFAULT_ANNUAL_MARGIN_RATE,
    output_png: str = "results/leverage_simulation.png"
) -> None:
    """
    Ejecuta el pipeline completo de análisis de apalancamiento e imprime el reporte en consola.
    """
    trades_path = f"results/trades_pca_sp100_{period}.csv"
    prices_path = "data/sp100_prices_10y.csv"

    if not os.path.exists(trades_path):
        # Fallback al archivo genérico si no existe
        if os.path.exists("results/trades_pca_sp100_10years.csv"):
            trades_path = "results/trades_pca_sp100_10years.csv"
            period = "10years"
        else:
            raise FileNotFoundError(f"No se encontró el archivo de trades: {trades_path}")

    period_labels = {
        "10years": "Horizonte 10 Años (2016–2025)",
        "7years": "Horizonte 7 Años (2019–2025)",
        "5years": "Horizonte 5 Años (2021–2025)"
    }
    label = period_labels.get(period, period)

    print("=" * 82)
    print(f"ANÁLISIS DE APALANCAMIENTO ÓPTIMO (CRITERIO DE KELLY) — S&P 100 STAT ARB")
    print(f"Periodo Analizado: {label}")
    print(f"Tasa de Margen Benchmark (Interactive Brokers): {annual_margin_rate:.2%} anual ({annual_margin_rate/TRADING_DAYS_PER_YEAR:.4%} diario)")
    print("=" * 82)

    # 1. Carga de serie de retornos diarios
    daily_returns = load_strategy_daily_returns(trades_path=trades_path, prices_path=prices_path)
    print(f"\n[1/4] Serie de Retornos Diarios Reconstruida:")
    print(f"      Total de barras de negociación: {len(daily_returns)} días hábiles")
    print(f"      Rango temporal observado       : {daily_returns.index[0].strftime('%Y-%m-%d')} a {daily_returns.index[-1].strftime('%Y-%m-%d')}")

    # 2. Cálculo estocástico de Kelly
    k = calculate_kelly_criterion(daily_returns, annual_margin_rate=annual_margin_rate)

    print(f"\n[2/4] Parametros Estocasticos y Multiplicadores de Kelly:")
    print(f"      - Retorno Medio Diario (mu)    : {k['mu_daily']:+.6f} ({k['mu_annual']:+.2%} anualizado)")
    print(f"      - Desviacion Estandar (sigma)  : {k['std_daily']:.6f} ({k['vol_annual']:.2%} anualizada)")
    print(f"      - Varianza Diaria (sigma^2)    : {k['var_daily']:.8f}")
    print(f"      - Tasa Costo Margen Diaria (rf): {k['rf_daily']:.6f} ({k['rf_annual']:.2%} anualizada)")
    print(f"      - Exceso de Retorno (mu - rf)  : {(k['mu_daily'] - k['rf_daily']):+.6f} ({(k['mu_annual'] - k['rf_annual']):+.2%} anualizado)")
    print("-" * 82)
    print(f"      >>> MULTIPLICADOR FULL KELLY (L*) : {k['full_kelly']:+.4f}x")
    print(f"      >>> MULTIPLICADOR HALF-KELLY (L*/2): {k['half_kelly']:+.4f}x")
    print("-" * 82)

    # Diagnóstico cuantitativo de Kelly
    if k["full_kelly"] <= 0.0:
        print("      [!] ADVERTENCIA CUANTITATIVA:")
        print("          El exceso de retorno sobre el costo de financiamiento (mu - rf) es NEGATIVO.")
        print("          En teoría de información y gestión de carteras, un multiplicador de Kelly negativo")
        print("          dicta que el apalancamiento óptimo es CERO (0x). Tomar deuda al 6.8% anual amplifica")
        print("          geométricamente las pérdidas y acelera el riesgo de ruina del fondo.")
    elif k["full_kelly"] < 1.0:
        print("      [i] INTERPRETACIÓN INSTITUCIONAL:")
        print("          El multiplicador de Kelly es positivo pero menor a 1.0x (0 < L* < 1).")
        print("          El modelo recomienda desapalancamiento: mantener una fracción en efectivo libre de riesgo")
        print("          y no solicitar crédito al broker, ya que el spread sobre el costo de margen no justifica")
        print("          el riesgo de la volatilidad adicional.")
    else:
        print("      [+] El modelo justifica matemáticamente el uso de apalancamiento moderado.")

    # 3. Simulación de curvas de capital para L = 1x, 2x, 3x y Half-Kelly
    half_kelly_effective = max(0.0, k["half_kelly"])
    leverage_levels = [1.0, 2.0, 3.0, half_kelly_effective]
    # Eliminar duplicados si Half-Kelly coincide
    leverage_levels = sorted(list(set(leverage_levels)))

    nav_df, dd_df, metrics = simulate_leveraged_curves(
        daily_returns=daily_returns,
        leverage_levels=leverage_levels,
        annual_margin_rate=annual_margin_rate
    )

    print(f"\n[3/4] Comparativa de Métricas de Desempeño por Nivel de Apalancamiento:")
    print("-" * 82)
    header = f"{'Nivel':<10} | {'Retorno Tot':<12} | {'CAGR':<8} | {'Vol Anual':<9} | {'Max DD':<9} | {'Sharpe':<7} | {'NAV Final ($)':<12}"
    print(header)
    print("-" * 82)
    for m in metrics:
        row = f"{m['label']:<10} | {m['total_return']:>11.2%} | {m['cagr']:>7.2%} | {m['annual_vol']:>8.2%} | {m['max_drawdown']:>8.2%} | {m['sharpe']:>7.2f} | ${m['final_nav']:>11,.2f}"
        print(row)
    print("-" * 82)

    # 4. Generación gráfica
    print(f"\n[4/4] Renderizando Curvas de Capital y Gráfico de Inmersión...")
    plot_leverage_simulation(nav_df=nav_df, dd_df=dd_df, period_label=label, output_png=output_png)

    print("=" * 82)
    print("OPTIMIZACIÓN DE APALANCAMIENTO FINALIZADA")
    print("=" * 82)


def main():
    parser = argparse.ArgumentParser(description="Optimización de Apalancamiento y Criterio de Kelly.")
    parser.add_argument("--period", type=str, default="10years", choices=["10years", "7years", "5years"], help="Periodo a evaluar (default: 10years).")
    parser.add_argument("--margin-rate", type=float, default=DEFAULT_ANNUAL_MARGIN_RATE, help="Tasa anual de margen (default: 0.068 = 6.8%).")
    parser.add_argument("--output", type=str, default="results/leverage_simulation.png", help="Ruta de salida para la gráfica.")
    args = parser.parse_args()

    run_leverage_optimization(
        period=args.period,
        annual_margin_rate=args.margin_rate,
        output_png=args.output
    )


if __name__ == "__main__":
    main()
