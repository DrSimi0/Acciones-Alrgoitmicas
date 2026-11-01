"""
Módulo de Extracción de Factores por Análisis de Componentes Principales (PCA) — src/pca_model.py.

Implementa el marco teórico de Arbitraje Estadístico Multivariado de Avellaneda & Lee (2010):
1. Estandarización de retornos de activos y descomposición espectral de la matriz de correlación empírica.
2. Selección dinámica de K componentes principales que explican el riesgo sistemático de mercado/sectorial.
3. Descomposición de retornos en factores sistemáticos y residuales idiosincrásicos mediante OLS.
4. Generación de series acumuladas de residuales (spreads sintéticos multivariados) para modelado OU.
"""

from typing import Dict, List, Optional, Tuple, Any, Union
import numpy as np
import pandas as pd
import statsmodels.api as sm


class PCAFactorModel:
    """
    Modelo de Factores Estadísticos basado en Componentes Principales (PCA)
    según la formulación de Avellaneda & Lee (2010).
    """

    def __init__(
        self,
        variance_threshold: float = 0.80,
        n_components: Optional[int] = None,
        use_svd: bool = True
    ):
        """
        Args:
            variance_threshold: Proporción mínima acumulada de varianza total a explicar (ej. 0.80 = 80%).
            n_components: Número fijo de componentes a retener. Si es None, se determina dinámicamente
                          mediante variance_threshold.
            use_svd: Si es True, utiliza Descomposición en Valores Singulares (SVD). Si es False,
                     utiliza descomposición de autovalores sobre la matriz de correlación.
        """
        if not (0.0 < variance_threshold <= 1.0):
            raise ValueError(f"variance_threshold debe estar en (0, 1], recibido {variance_threshold}")
        if n_components is not None and n_components <= 0:
            raise ValueError(f"n_components debe ser un entero positivo, recibido {n_components}")

        self.variance_threshold = variance_threshold
        self.n_components = n_components
        self.use_svd = use_svd

        # Atributos estimados durante fit
        self.asset_names_: List[str] = []
        self.means_: Optional[pd.Series] = None
        self.stds_: Optional[pd.Series] = None
        self.eigenvalues_: Optional[np.ndarray] = None
        self.eigenvectors_: Optional[np.ndarray] = None
        self.components_: Optional[pd.DataFrame] = None
        self.explained_variance_ratio_: Optional[np.ndarray] = None
        self.cumulative_variance_ratio_: Optional[np.ndarray] = None
        self.n_components_: int = 0
        self.factor_names_: List[str] = []
        self.factor_returns_: Optional[pd.DataFrame] = None
        self.factor_loadings_: Optional[pd.DataFrame] = None
        self.alphas_: Optional[pd.Series] = None
        self.r2_scores_: Optional[pd.Series] = None
        self.in_sample_residuals_: Optional[pd.DataFrame] = None
        self.in_sample_cumulative_residuals_: Optional[pd.DataFrame] = None
        self.is_fitted_: bool = False

    def fit(self, returns_df: pd.DataFrame) -> "PCAFactorModel":
        """
        Ajusta el modelo PCA sobre la matriz de retornos del periodo de formación.

        1. Estandariza los retornos: Z = (R - mean) / std.
        2. Calcula autovalores y autovectores (vía SVD o eigendecomposición de la correlación).
        3. Selecciona los K factores que superan variance_threshold.
        4. Estima las cargas factoriales (betas) y alphas de cada activo mediante regresión OLS.

        Args:
            returns_df: DataFrame (T x N) con retornos periódicos de los N activos.

        Returns:
            self con los parámetros factoriales y residuales estimados.
        """
        if not isinstance(returns_df, pd.DataFrame):
            raise TypeError("returns_df debe ser una instancia de pd.DataFrame")
        if returns_df.empty or returns_df.shape[1] < 2:
            raise ValueError("returns_df debe contener al menos 2 activos y observaciones válidas")

        clean_returns = returns_df.dropna()
        n_obs, n_assets = clean_returns.shape
        if n_obs < n_assets:
            # Advertencia o manejo de matriz mal condicionada
            pass

        self.asset_names_ = list(clean_returns.columns)
        self.means_ = clean_returns.mean()
        self.stds_ = clean_returns.std(ddof=1)

        # Prevenir divisiones por cero en caso de series constantes
        zero_std = self.stds_ <= 1e-8
        if zero_std.any():
            invalid_assets = list(self.stds_[zero_std].index)
            raise ValueError(f"Los siguientes activos presentan desviación estándar nula: {invalid_assets}")

        # Retornos estandarizados: Y_it = (R_it - mean_i) / std_i
        standardized_returns = (clean_returns - self.means_) / self.stds_
        Z = standardized_returns.values  # (T x N)

        if self.use_svd:
            # SVD: Z / sqrt(T - 1) = U @ diag(s) @ Vt
            # Los autovalores de la matriz de correlación son s^2
            scaled_Z = Z / np.sqrt(n_obs - 1)
            U, s, Vt = np.linalg.svd(scaled_Z, full_matrices=False)
            eigenvalues = s ** 2
            # Las columnas de V (filas de Vt transpuestas) son los autovectores
            eigenvectors = Vt.T
        else:
            # Matriz de correlación empírica C = (Z.T @ Z) / (T - 1)
            corr_mat = (Z.T @ Z) / (n_obs - 1)
            vals, vecs = np.linalg.eigh(corr_mat)
            # eigh devuelve autovalores en orden ascendente; ordenamos descendente
            idx_sort = np.argsort(vals)[::-1]
            eigenvalues = vals[idx_sort]
            eigenvectors = vecs[:, idx_sort]

        # Asegurar autovalores no negativos por precisión numérica
        eigenvalues = np.maximum(eigenvalues, 0.0)
        total_var = np.sum(eigenvalues)
        if total_var <= 1e-12:
            raise ValueError("Varianza total nula en la matriz de retornos")

        explained_ratio = eigenvalues / total_var
        cum_explained_ratio = np.cumsum(explained_ratio)

        # Selección de K componentes
        if self.n_components is not None:
            k = min(self.n_components, n_assets)
        else:
            # Mínimo número de componentes para superar variance_threshold
            k_candidates = np.where(cum_explained_ratio >= self.variance_threshold)[0]
            k = int(k_candidates[0] + 1) if len(k_candidates) > 0 else n_assets

        self.n_components_ = k
        self.eigenvalues_ = eigenvalues
        self.eigenvectors_ = eigenvectors
        self.explained_variance_ratio_ = explained_ratio
        self.cumulative_variance_ratio_ = cum_explained_ratio
        self.factor_names_ = [f"PC{i+1}" for i in range(k)]

        # Autovectores de los K factores seleccionados: shape (N x K)
        V_k = eigenvectors[:, :k]
        self.components_ = pd.DataFrame(
            V_k,
            index=self.asset_names_,
            columns=self.factor_names_
        )

        # Retornos factoriales in-sample: F = Z @ V_k -> shape (T x K)
        factor_returns_matrix = Z @ V_k
        self.factor_returns_ = pd.DataFrame(
            factor_returns_matrix,
            index=clean_returns.index,
            columns=self.factor_names_
        )

        # Regresión OLS de cada activo contra los K factores:
        # R_{i,t} = alpha_i + sum_k beta_{i,k} * F_{k,t} + epsilon_{i,t}
        # Matriz de diseño con constante: X = [1, F]
        X_design = sm.add_constant(factor_returns_matrix)  # shape (T x K+1)
        # Estimación eficiente simultánea por mínimos cuadrados ordinarios:
        # beta_full = (X.T @ X)^(-1) @ X.T @ clean_returns.values -> shape (K+1 x N)
        beta_full, _, _, _ = np.linalg.lstsq(X_design, clean_returns.values, rcond=None)

        alphas = beta_full[0, :]  # shape (N,)
        loadings = beta_full[1:, :]  # shape (K x N) -> transponer a (N x K)

        self.alphas_ = pd.Series(alphas, index=self.asset_names_, name="alpha")
        self.factor_loadings_ = pd.DataFrame(
            loadings.T,
            index=self.asset_names_,
            columns=self.factor_names_
        )

        # Predicciones y cálculo de residuales idiosincrásicos in-sample:
        # R_hat = X_design @ beta_full -> shape (T x N)
        predicted_returns = X_design @ beta_full
        residuals_matrix = clean_returns.values - predicted_returns

        self.in_sample_residuals_ = pd.DataFrame(
            residuals_matrix,
            index=clean_returns.index,
            columns=self.asset_names_
        )

        # Spread sintético acumulado: X_{i,t} = sum_{s=1}^t epsilon_{i,s}
        self.in_sample_cumulative_residuals_ = self.in_sample_residuals_.cumsum()

        # R2 score para cada activo
        sst = np.sum((clean_returns.values - self.means_.values) ** 2, axis=0)
        sse = np.sum(residuals_matrix ** 2, axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            r2 = 1.0 - (sse / sst)
            r2 = np.nan_to_num(r2, nan=0.0)
        self.r2_scores_ = pd.Series(r2, index=self.asset_names_, name="r2")

        self.is_fitted_ = True
        return self

    def transform(self, returns_df: pd.DataFrame) -> pd.DataFrame:
        """
        Proyecta retornos (por ejemplo, fuera de muestra) en el espacio de factores congelado.

        F_{oos} = ((R_{oos} - mean_in) / std_in) @ V_k

        Args:
            returns_df: DataFrame con retornos de los activos con las mismas columnas que el modelo entrenado.

        Returns:
            DataFrame con retornos de los factores K proyectados.
        """
        self._check_is_fitted()
        if not isinstance(returns_df, pd.DataFrame):
            raise TypeError("returns_df debe ser una instancia de pd.DataFrame")

        missing_cols = set(self.asset_names_) - set(returns_df.columns)
        if missing_cols:
            raise ValueError(f"Faltan columnas requeridas en returns_df: {missing_cols}")

        aligned = returns_df[self.asset_names_].dropna()
        standardized = (aligned - self.means_) / self.stds_
        v_k = self.components_.values  # (N x K)

        factors = standardized.values @ v_k
        return pd.DataFrame(
            factors,
            index=aligned.index,
            columns=self.factor_names_
        )

    def get_idiosyncratic_residuals(
        self,
        returns_df: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Calcula la serie temporal acumulada de los residuales idiosincrásicos:
        X_{i,t} = sum_{s=1}^t epsilon_{i,s}

        Representa el spread sintético multivariado de cada activo respecto al mercado/sector.

        Args:
            returns_df: DataFrame de retornos. Si es None, retorna los residuales in-sample del fit.
                        Si se proporciona, proyecta fuera de muestra empleando los parámetros congelados.

        Returns:
            DataFrame con la serie temporal acumulada de residuales X_{i,t} para cada activo.
        """
        self._check_is_fitted()

        if returns_df is None:
            return self.in_sample_cumulative_residuals_.copy()

        aligned = returns_df[self.asset_names_].dropna()
        if aligned.empty:
            return pd.DataFrame(columns=self.asset_names_)

        # Proyectar retornos a factores
        factor_returns = self.transform(aligned)
        x_design = sm.add_constant(factor_returns.values)  # (T_oos x K+1)

        # Reconstruir beta_full: [alpha, loadings.T] -> shape (K+1 x N)
        beta_full = np.vstack([self.alphas_.values, self.factor_loadings_.values.T])

        predicted = x_design @ beta_full
        residuals = aligned.values - predicted

        df_residuals = pd.DataFrame(
            residuals,
            index=aligned.index,
            columns=self.asset_names_
        )
        return df_residuals.cumsum()

    def get_factor_returns(self, returns_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Retorna la serie temporal de retornos de los factores K.

        Args:
            returns_df: Si es None, retorna los factores in-sample estimados en fit().
                        Si se proporciona, proyecta los retornos sobre los autovectores congelados.
        """
        self._check_is_fitted()
        if returns_df is None:
            return self.factor_returns_.copy()
        return self.transform(returns_df)

    def _check_is_fitted(self) -> None:
        """Verifica que el modelo haya sido ajustado previamente."""
        if not self.is_fitted_:
            raise RuntimeError("El modelo PCAFactorModel no ha sido ajustado. Llame a fit() primero.")
