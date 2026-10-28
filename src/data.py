"""
Módulo de Ingesta, Procesamiento y Ajuste de Datos (data.py).

Maneja datos point-in-time, ajustes corporativos (splits, dividendos),
construcción de series continuas de futuros (Panamá / Proporcional) y
generación de datos sintéticos controlados para pruebas unitarias.
"""

from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np


class CorporateActionAdjuster:
    """
    Ajusta series de precios de acciones por splits de acciones y dividendos en efectivo.
    """

    @staticmethod
    def adjust_splits_and_dividends(
        raw_prices: pd.Series,
        splits: Optional[pd.Series] = None,
        dividends: Optional[pd.Series] = None
    ) -> pd.Series:
        """
        Calcula la serie de precios de cierre ajustados hacia atrás (backward-adjusted),
        garantizando que la última barra conserve el precio nominal actual.

        Args:
            raw_prices: Serie cronológica de precios de cierre sin ajustar.
            splits: Serie con ratios de split (ej. 2.0 para un split 2-for-1).
            dividends: Serie con dividendos en efectivo por acción.

        Returns:
            pd.Series de precios ajustados continuos.
        """
        adj_prices = raw_prices.astype(float).copy()
        n = len(adj_prices)

        split_factors = pd.Series(1.0, index=adj_prices.index)
        div_factors = pd.Series(1.0, index=adj_prices.index)

        if splits is not None:
            for dt, ratio in splits.items():
                if dt in split_factors.index and ratio > 0:
                    split_factors.loc[dt] = ratio

        if dividends is not None:
            for dt, div in dividends.items():
                if dt in div_factors.index and dt in raw_prices.index:
                    p = raw_prices.loc[dt]
                    if p > 0:
                        div_factors.loc[dt] = (p - div) / p

        # Factor multiplicador acumulado hacia atrás
        total_factors = split_factors * div_factors
        # El ajuste retroactivo multiplica desde el final hacia el principio
        cumulative_adjustment = total_factors[::-1].cumprod()[::-1].shift(-1, fill_value=1.0)

        # Para splits, el precio anterior al split se divide por el ratio (multiplica por 1/ratio)
        # Aseguramos consistencia estándar financiera:
        adj_prices = raw_prices * cumulative_adjustment
        return adj_prices


class ContinuousFuturesBuilder:
    """
    Construye series continuas de futuros para evitar distorsiones por vencimientos.
    """

    @staticmethod
    def panama_stitch(
        contracts: List[pd.Series],
        roll_indices: List[int]
    ) -> pd.Series:
        """
        Ajuste de Panamá (Aditivo): Desplaza hacia atrás las series sumando la diferencia
        de precios en el momento del rollover. Conserva exactamente las diferencias
        absolutas de precio (spread) y las propiedades de cointegración.

        Args:
            contracts: Lista de pd.Series ordenadas cronológicamente por vencimiento.
            roll_indices: Índices de barra en los que se ejecuta el cambio de contrato.

        Returns:
            pd.Series continua ajustada aditivamente.
        """
        if not contracts:
            raise ValueError("La lista de contratos no puede estar vacía.")

        if len(contracts) == 1:
            return contracts[0].copy()

        # Comenzamos con el contrato activo más reciente (sin desplazar)
        full_series = contracts[-1].copy()
        cumulative_shift = 0.0

        for i in range(len(contracts) - 2, -1, -1):
            earlier = contracts[i]
            later = contracts[i + 1]

            # Encontrar el punto de solape en roll_indices
            roll_idx = roll_indices[i] if i < len(roll_indices) else min(len(earlier), len(later)) - 1
            roll_date = earlier.index[roll_idx]

            # Salto de rollover: precio del contrato entrante - precio del saliente
            p_later = later.loc[roll_date] if roll_date in later.index else later.iloc[0]
            p_earlier = earlier.loc[roll_date]

            shift = p_later - p_earlier
            cumulative_shift += shift

            adjusted_earlier = earlier.loc[:roll_date].iloc[:-1] + cumulative_shift
            full_series = pd.concat([adjusted_earlier, full_series])

        return full_series.sort_index()

    @staticmethod
    def proportional_stitch(
        contracts: List[pd.Series],
        roll_indices: List[int]
    ) -> pd.Series:
        """
        Ajuste Proporcional (Multiplicativo): Escala las series anteriores mediante el ratio
        de precios en el rollover para preservar los retornos porcentuales geométricos.
        """
        if not contracts:
            raise ValueError("La lista de contratos no puede estar vacía.")

        if len(contracts) == 1:
            return contracts[0].copy()

        full_series = contracts[-1].copy()
        cumulative_ratio = 1.0

        for i in range(len(contracts) - 2, -1, -1):
            earlier = contracts[i]
            later = contracts[i + 1]

            roll_idx = roll_indices[i] if i < len(roll_indices) else min(len(earlier), len(later)) - 1
            roll_date = earlier.index[roll_idx]

            p_later = later.loc[roll_date] if roll_date in later.index else later.iloc[0]
            p_earlier = earlier.loc[roll_date]

            ratio = p_later / p_earlier if p_earlier != 0 else 1.0
            cumulative_ratio *= ratio

            adjusted_earlier = earlier.loc[:roll_date].iloc[:-1] * cumulative_ratio
            full_series = pd.concat([adjusted_earlier, full_series])

        return full_series.sort_index()


class SyntheticMarketDataGenerator:
    """
    Generador de series sintéticas deterministas para pruebas unitarias sin dependencias externas.
    """

    @staticmethod
    def generate_cointegrated_pair(
        n_bars: int = 500,
        beta: float = 1.5,
        alpha: float = 10.0,
        ou_kappa: float = 0.15,
        seed: int = 42
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Genera un par sintético cointegrado donde:
        - X_t es un paseo aleatorio I(1)
        - spread_t es un proceso estacionario Ornstein-Uhlenbeck I(0)
        - Y_t = alpha + beta * X_t + spread_t
        """
        rng = np.random.default_rng(seed)
        dates = pd.date_range("2023-01-01", periods=n_bars, freq="B")

        # Paseo aleatorio para el activo X
        x_innovations = rng.normal(0, 1.0, size=n_bars)
        x_prices = 100.0 + np.cumsum(x_innovations)

        # Proceso Ornstein-Uhlenbeck para el spread
        # dS = -kappa * S dt + sigma * dW
        spread = np.zeros(n_bars)
        sigma = 0.5
        for t in range(1, n_bars):
            spread[t] = spread[t - 1] - ou_kappa * spread[t - 1] + sigma * rng.normal()

        y_prices = alpha + beta * x_prices + spread

        s_x = pd.Series(x_prices, index=dates, name="ASSET_X")
        s_y = pd.Series(y_prices, index=dates, name="ASSET_Y")
        return s_y, s_x

    @staticmethod
    def generate_random_walks(
        n_assets: int = 10,
        n_bars: int = 500,
        seed: int = 123
    ) -> pd.DataFrame:
        """
        Genera una matriz de paseos aleatorios independientes no cointegrados.
        """
        rng = np.random.default_rng(seed)
        dates = pd.date_range("2023-01-01", periods=n_bars, freq="B")
        data = {}

        for i in range(n_assets):
            innovations = rng.normal(0, 1.0, size=n_bars)
            data[f"STOCK_{i:02d}"] = 50.0 + np.cumsum(innovations)

        return pd.DataFrame(data, index=dates)
