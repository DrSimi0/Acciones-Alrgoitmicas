"""
Módulo de Gestión de Universo y Particionado Temporal (universe.py).

Garantiza la sincronización de activos y la partición estricta Walk-Forward
sin sesgo prospectivo (look-ahead bias).
"""

from typing import List, Tuple, Dict, Optional
import pandas as pd
import numpy as np


class UniverseManager:
    """
    Gestiona el universo de activos, filtra por liquidez/calidad de datos
    y sincroniza calendarios de negociación.
    """

    def __init__(self, tickers: Optional[List[str]] = None, min_history_bars: int = 252):
        """
        Args:
            tickers: Lista de símbolos que componen el universo.
            min_history_bars: Mínimo número de barras requeridas para considerar un activo válido.
        """
        self.tickers = list(tickers) if tickers is not None else []
        self.min_history_bars = min_history_bars

    def filter_active_tickers(self, prices: pd.DataFrame, max_nan_ratio: float = 0.02) -> List[str]:
        """
        Filtra activos que tengan suficiente historial y un ratio de valores nulos admisible.

        Args:
            prices: DataFrame con columnas por ticker y fechas en el índice.
            max_nan_ratio: Proporción máxima de NaNs tolerada antes de descartar el activo.

        Returns:
            Lista de tickers que cumplen con los requisitos de calidad.
        """
        valid_tickers = []
        total_bars = len(prices)

        for col in prices.columns:
            series = prices[col]
            valid_bars = series.dropna().shape[0]
            nan_ratio = series.isna().sum() / total_bars if total_bars > 0 else 1.0

            if valid_bars >= self.min_history_bars and nan_ratio <= max_nan_ratio:
                valid_tickers.append(col)

        return valid_tickers

    def synchronize_universe(self, prices: pd.DataFrame, forward_fill_limit: int = 2) -> pd.DataFrame:
        """
        Sincroniza las fechas del universo de activos mediante intersección
        y relleno hacia adelante estricto (point-in-time) hasta un límite.

        Args:
            prices: Matriz de precios brutos.
            forward_fill_limit: Máximo de barras consecutivas a rellenar con el último precio observado.

        Returns:
            DataFrame limpio con fechas comunes y sin NaNs.
        """
        # Orden temporal estricto
        synced = prices.sort_index().copy()

        # Relleno hacia adelante (solo hasta el límite para no inventar precios si se suspende la cotización)
        if forward_fill_limit > 0:
            synced = synced.ffill(limit=forward_fill_limit)

        # Se descartan filas residuales con NaNs para garantizar sincronización perfecta
        synced = synced.dropna()
        return synced

    @staticmethod
    def get_walk_forward_splits(
        data: pd.DataFrame,
        formation_bars: int = 252,
        trading_bars: int = 63,
        step_bars: Optional[int] = None
    ) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
        """
        Genera particiones cronológicas Walk-Forward estrictas.

        Args:
            data: DataFrame indexado por fecha.
            formation_bars: Número de barras del periodo de formación (In-Sample).
            trading_bars: Número de barras del periodo de negociación (Out-of-Sample).
            step_bars: Desplazamiento temporal entre ventanas consecutivas (por defecto = trading_bars).

        Returns:
            Lista de tuplas (df_formation, df_trading).
        """
        if step_bars is None:
            step_bars = trading_bars

        n_bars = len(data)
        splits = []
        start_idx = 0

        while start_idx + formation_bars + trading_bars <= n_bars:
            formation_end = start_idx + formation_bars
            trading_end = formation_end + trading_bars

            formation_data = data.iloc[start_idx:formation_end].copy()
            trading_data = data.iloc[formation_end:trading_end].copy()

            splits.append((formation_data, trading_data))
            start_idx += step_bars

        return splits


class WalkForwardSplitter:
    """
    Particionador temporal para análisis Walk-Forward estricto sin look-ahead bias.
    """

    @staticmethod
    def split(
        data: pd.DataFrame,
        formation_bars: int = 252,
        trading_bars: int = 63,
        step_bars: Optional[int] = None
    ) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
        """
        Divide la serie histórica en ventanas rodantes cronológicas de formación y negociación.
        """
        return UniverseManager.get_walk_forward_splits(
            data=data,
            formation_bars=formation_bars,
            trading_bars=trading_bars,
            step_bars=step_bars
        )
