"""
Pruebas unitarias para el modelo de factores PCA multivariado (src/pca_model.py).
"""

import pytest
import numpy as np
import pandas as pd

from src.pca_model import PCAFactorModel


class TestPCAFactorModel:

    @pytest.fixture
    def synthetic_multivariate_returns(self):
        """
        Genera una matriz sintética de retornos con 5 activos y estructura factorial latente:
        Factor 1 (Mercado general) + Factor 2 (Subsector) + Ruido idiosincrásico.
        """
        rng = np.random.default_rng(42)
        n_bars = 252
        dates = pd.date_range("2023-01-01", periods=n_bars, freq="B")

        # 2 factores comunes latentes
        f1 = rng.normal(0, 0.015, n_bars)  # Mercado
        f2 = rng.normal(0, 0.010, n_bars)  # Sector

        # Activos con diferentes cargas factoriales
        r_a = 1.2 * f1 + 0.8 * f2 + rng.normal(0, 0.005, n_bars)
        r_b = 1.0 * f1 + 0.9 * f2 + rng.normal(0, 0.005, n_bars)
        r_c = 0.9 * f1 - 0.5 * f2 + rng.normal(0, 0.006, n_bars)
        r_d = 0.8 * f1 - 0.4 * f2 + rng.normal(0, 0.006, n_bars)
        r_e = 0.5 * f1 + 0.1 * f2 + rng.normal(0, 0.007, n_bars)

        df = pd.DataFrame(
            {"ASSET_A": r_a, "ASSET_B": r_b, "ASSET_C": r_c, "ASSET_D": r_d, "ASSET_E": r_e},
            index=dates
        )
        return df

    def test_fit_and_orthogonality(self, synthetic_multivariate_returns):
        model = PCAFactorModel(variance_threshold=0.80, use_svd=True)
        model.fit(synthetic_multivariate_returns)

        assert model.is_fitted_ is True
        assert model.n_components_ >= 1
        assert len(model.asset_names_) == 5
        assert len(model.eigenvalues_) == 5

        # Los autovalores deben estar ordenados descendentemente y ser >= 0
        diffs = np.diff(model.eigenvalues_)
        assert (diffs <= 1e-10).all()
        assert (model.eigenvalues_ >= 0).all()

        # Los autovectores deben ser ortonormales: V^T @ V = I
        V = model.eigenvectors_
        identity_approx = V.T @ V
        assert np.allclose(identity_approx, np.eye(5), atol=1e-8)

        # Los retornos de los factores K deben estar descorrelacionados
        f_rets = model.factor_returns_.values
        cov_factors = np.cov(f_rets, rowvar=False)
        if model.n_components_ > 1:
            # Los elementos fuera de la diagonal deben ser prácticamente cero
            diag = np.diag(cov_factors)
            corr_factors = cov_factors / np.sqrt(np.outer(diag, diag))
            off_diag = corr_factors - np.eye(model.n_components_)
            assert np.allclose(off_diag, 0.0, atol=1e-6)

    def test_dynamic_variance_threshold_selection(self, synthetic_multivariate_returns):
        # Con un umbral bajo (0.50), debe requerir menos componentes que con un umbral alto (0.95)
        model_low = PCAFactorModel(variance_threshold=0.50).fit(synthetic_multivariate_returns)
        model_high = PCAFactorModel(variance_threshold=0.95).fit(synthetic_multivariate_returns)

        assert model_low.n_components_ <= model_high.n_components_
        assert model_low.cumulative_variance_ratio_[model_low.n_components_ - 1] >= 0.50
        assert model_high.cumulative_variance_ratio_[model_high.n_components_ - 1] >= 0.95

    def test_fixed_n_components(self, synthetic_multivariate_returns):
        model = PCAFactorModel(n_components=2).fit(synthetic_multivariate_returns)
        assert model.n_components_ == 2
        assert model.components_.shape == (5, 2)
        assert model.factor_returns_.shape == (252, 2)
        assert model.factor_loadings_.shape == (5, 2)

    def test_idiosyncratic_residuals_and_cumulative_series(self, synthetic_multivariate_returns):
        model = PCAFactorModel(variance_threshold=0.80).fit(synthetic_multivariate_returns)
        residuals_cum = model.get_idiosyncratic_residuals()

        # Las dimensiones e índice deben coincidir exactamente con el dataset de entrada
        assert residuals_cum.shape == synthetic_multivariate_returns.shape
        assert (residuals_cum.index == synthetic_multivariate_returns.index).all()
        assert list(residuals_cum.columns) == list(synthetic_multivariate_returns.columns)

        # Los residuales de la regresión OLS deben tener media in-sample prácticamente cero
        in_sample_res = model.in_sample_residuals_
        assert np.allclose(in_sample_res.mean().values, 0.0, atol=1e-7)

    def test_out_of_sample_projection_consistency(self, synthetic_multivariate_returns):
        in_sample = synthetic_multivariate_returns.iloc[:200]
        out_of_sample = synthetic_multivariate_returns.iloc[200:]

        model = PCAFactorModel(variance_threshold=0.85).fit(in_sample)
        oos_factors = model.transform(out_of_sample)
        oos_cum_residuals = model.get_idiosyncratic_residuals(out_of_sample)

        assert len(oos_factors) == len(out_of_sample)
        assert len(oos_cum_residuals) == len(out_of_sample)
        assert (oos_cum_residuals.index == out_of_sample.index).all()

        # Verificar que fit() no se vio afectado por el out-of-sample (no data leakage)
        assert len(model.in_sample_residuals_) == 200

    def test_svd_vs_eigendecomposition_consistency(self, synthetic_multivariate_returns):
        # Ambos métodos deben generar valores idénticos de varianza explicada
        model_svd = PCAFactorModel(variance_threshold=0.85, use_svd=True).fit(synthetic_multivariate_returns)
        model_eig = PCAFactorModel(variance_threshold=0.85, use_svd=False).fit(synthetic_multivariate_returns)

        assert model_svd.n_components_ == model_eig.n_components_
        assert np.allclose(model_svd.eigenvalues_, model_eig.eigenvalues_, atol=1e-7)
        assert np.allclose(model_svd.explained_variance_ratio_, model_eig.explained_variance_ratio_, atol=1e-7)
