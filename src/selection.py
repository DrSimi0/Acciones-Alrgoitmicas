"""
Módulo de Preselección por Distancia (selection.py) — Fase 1 del Embudo.

Calcula la Suma de Desviaciones Cuadradas (SSD) sobre log-precios estandarizados
para reducir el espacio combinatorio O(N^2) al subconjunto Top-K de activos
que presentan mayor proximidad histórica en el periodo de formación.
"""

from typing import List, Tuple, Optional
import itertools
import pandas as pd
import numpy as np


class DistancePreselector:
    """
    Filtro de preselección rápida basado en distancia euclidiana (SSD)
    sobre log-precios estandarizados para evitar sesgos por precio base.
    """

    def __init__(self, top_n_pairs: int = 20, min_std: float = 1e-6):
        """
        Args:
            top_n_pairs: Número máximo de pares candidatos a seleccionar.
            min_std: Umbral mínimo de desviación estándar para descartar activos planos.
        """
        self.top_n_pairs = top_n_pairs
        self.min_std = min_std

    def normalize_prices(self, prices: pd.DataFrame) -> pd.DataFrame:
        """
        Normaliza las series de precios mediante log-precios estandarizados longitudinalmente:
        z_{i, t} = (ln(P_{i, t}) - mean(ln(P_i))) / std(ln(P_i)).

        Esto asegura invarianza de escala y elimina la dependencia artificial del valor nominal en t=0.

        Args:
            prices: Matriz de precios de formación (índice: fechas, columnas: tickers).

        Returns:
            DataFrame con las series de log-precios estandarizadas (media 0, varianza 1).
        """
        if (prices <= 0).any().any():
            raise ValueError("Los precios deben ser estrictamente positivos para el cálculo logarítmico.")

        log_prices = np.log(prices)
        stds = log_prices.std(axis=0, ddof=1)

        # Filtrar activos sin volatilidad
        valid_cols = stds[stds > self.min_std].index
        if len(valid_cols) < 2:
            raise ValueError("No hay suficientes activos con volatilidad válida para formar pares.")

        log_prices = log_prices[valid_cols]
        means = log_prices.mean(axis=0)
        stds = log_prices.std(axis=0, ddof=1)

        standardized = (log_prices - means) / stds
        return standardized

    def compute_pairwise_ssd(self, normalized_prices: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula de forma vectorizada la Suma de Desviaciones Cuadradas (SSD)
        para todos los pares posibles N * (N - 1) / 2.

        Para series estandarizadas con varianza muestral 1 y media 0:
        SSD(i, j) = sum_t (z_{i, t} - z_{j, t})^2 = 2 * (T - 1) * (1 - r_{i, j})

        Args:
            normalized_prices: DataFrame de log-precios estandarizados.

        Returns:
            DataFrame ordenado ascendentemente por 'ssd', con columnas:
            ['asset_a', 'asset_b', 'ssd', 'correlation'].
        """
        tickers = list(normalized_prices.columns)
        n = len(tickers)
        t_bars = len(normalized_prices)

        if n < 2 or t_bars < 2:
            return pd.DataFrame(columns=["asset_a", "asset_b", "ssd", "correlation"])

        # Matriz de correlación de Pearson sobre las series estandarizadas
        corr_matrix = normalized_prices.corr().values
        records = []

        # Recorremos la mitad triangular superior estricta
        for i in range(n):
            for j in range(i + 1, n):
                r = float(corr_matrix[i, j])
                # SSD exacta calculada vectorialmente a partir de correlación
                ssd = 2.0 * (t_bars - 1) * max(0.0, 1.0 - r)
                records.append({
                    "asset_a": tickers[i],
                    "asset_b": tickers[j],
                    "ssd": float(ssd),
                    "correlation": r
                })

        df_ssd = pd.DataFrame(records)
        df_ssd = df_ssd.sort_values(by="ssd", ascending=True).reset_index(drop=True)
        return df_ssd

    def select_top_candidates(
        self,
        formation_prices: pd.DataFrame,
        min_correlation: float = 0.50
    ) -> pd.DataFrame:
        """
        Ejecuta el pipeline de preselección (Paso 1 del Funnel):
        1. Normalización de log-precios.
        2. Cálculo vectorizado de SSD y correlación.
        3. Filtrado por correlación mínima.
        4. Selección de los Top-K pares con menor distancia.

        Args:
            formation_prices: Precios brutos durante la ventana de formación.
            min_correlation: Filtro complementario de correlación mínima en el periodo.

        Returns:
            DataFrame con el Top-K de pares seleccionados y sus métricas.
        """
        norm = self.normalize_prices(formation_prices)
        df_pairs = self.compute_pairwise_ssd(norm)

        if min_correlation > -1.0:
            df_pairs = df_pairs[df_pairs["correlation"] >= min_correlation]

        top_candidates = df_pairs.head(self.top_n_pairs).copy().reset_index(drop=True)
        return top_candidates
