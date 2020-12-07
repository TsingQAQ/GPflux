# Copyright (C) PROWLER.io 2018 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential

import numpy as np
import pytest
import tensorflow as tf
from tqdm import tqdm

import gpflow

from gpflux.invariance.features import InvariantInducingPoints, StochasticInvariantInducingPoints
from gpflux.invariance.kernels import Invariant, StochasticInvariant
from gpflux.invariance.orbits import FlipInputDims, Permutation, QuantRotation, Rot90


@pytest.mark.parametrize("orbit,orbit_kwargs", [(FlipInputDims, {}),
                                                (Rot90, {}),
                                                (QuantRotation, {"rotation_quantisation": 90}),
                                                (Permutation, {})])
def test_invariant_kernels(session_tf, orbit, orbit_kwargs):
    X = np.random.randn(1, 2 ** 2)
    o = orbit(**orbit_kwargs)
    k = Invariant(X.shape[1], gpflow.kernels.SquaredExponential(X.shape[1]), o)

    # The kernel must evaluate to the same value for all points in the orbit
    # assert len(np.unique(k.compute_K_symm(k.orbit.compute_orbit(X).reshape(-1, X.shape[1])))) == 1
    assert np.std(k.compute_K_symm(k.orbit.compute_orbit(X).reshape(-1, X.shape[1]))) < 1e-15

    # Orbit size must be correctly mentioned
    assert k.orbit.compute_orbit(X).shape[1] == k.orbit.orbit_size


@pytest.mark.parametrize("orbit", [FlipInputDims, Rot90, QuantRotation, Permutation])
def test_kernel_diagonals(session_tf, orbit):
    X = np.random.randn(1, 2 ** 2)
    o = orbit()
    k = Invariant(X.shape[1], gpflow.kernels.SquaredExponential(X.shape[1]), o)
    Kd = np.diag(k.compute_K_symm(X))
    assert np.all(np.equal(Kd, k.compute_Kdiag(X)))


@pytest.mark.parametrize("orbit,stoch_orbit_kwargs", [
    (FlipInputDims, {"orbit_batch_size": 2}),
    (Rot90, {"orbit_batch_size": 3}),
    (QuantRotation, {"orbit_batch_size": 7}),
])
def test_invariant_predictions(session_tf, orbit, stoch_orbit_kwargs):
    np.random.seed(30452987)
    tf.set_random_seed(203485)
    N = 100
    X = np.random.randn(N, 2 ** 2)
    Xt = np.random.randn(N, 2 ** 2)
    orbit_kwargs = {}

    # Generate data
    k = Invariant(X.shape[1], gpflow.kernels.SquaredExponential(X.shape[1]), orbit(**orbit_kwargs))
    K = k.compute_K_symm(X) + np.eye(len(X)) * 0.1 ** 2.0
    L = np.linalg.cholesky(K)
    Y = L @ np.random.randn(len(X), 1)

    #
    # First, test inducing points against inducing features
    #
    f = gpflow.features.InducingPoints(X)
    ipm = gpflow.models.SGPR(X, Y, k, f)  # inducing point model
    ipm.likelihood.variance.assign(0.1 ** 2.0)
    # gpflow.train.ScipyOptimizer().minimize(ipm)

    k = Invariant(X.shape[1], gpflow.kernels.SquaredExponential(X.shape[1]), orbit(**orbit_kwargs))
    f = InvariantInducingPoints(k.orbit.compute_orbit(X).reshape(-1, X.shape[1]))
    idm = gpflow.models.SGPR(X, Y, k, f)  # inter-domain model
    idm.likelihood.variance.assign(0.1 ** 2.0)
    # gpflow.train.ScipyOptimizer().minimize(idm)

    pred_ipm = ipm.predict_f(Xt)
    pred_idm = idm.predict_f(Xt)

    for ip, id in zip(pred_ipm, pred_idm):
        pd = np.max(np.abs(id - ip) / ip) * 100
        assert pd < 0.5


@pytest.mark.parametrize("orbit_batch_size,samples,lml_samples", [
    (6, 1, 1),
    (5, 200, 200),
    # (3, 200, 1000),
    # (2, 300, 10000000)
])
def test_stochastic_predictions(session_tf, orbit_batch_size, samples, lml_samples):
    np.random.seed(30452987)
    tf.set_random_seed(203485)
    N = 100
    D = 3
    M = 400
    sig = 0.1 ** 2.

    X = np.random.randn(N, D)
    Xt = np.random.randn(N, D)
    stoch_orbit_kwargs = {"orbit_batch_size": orbit_batch_size}

    # Generate data
    k = Invariant(X.shape[1], gpflow.kernels.SquaredExponential(D), Permutation())
    K = k.compute_K_symm(X) + np.eye(len(X)) * sig
    L = np.linalg.cholesky(K)
    Y = L @ np.random.randn(len(X), 1)

    k = Invariant(X.shape[1], gpflow.kernels.SquaredExponential(D), Permutation())
    f = InvariantInducingPoints(np.random.randn(M, D))
    idm = gpflow.models.SGPR(X, Y, k, f)  # inter-domain model
    idm.likelihood.variance.assign(sig)

    k = StochasticInvariant(X.shape[1], gpflow.kernels.SquaredExponential(D),
                            Permutation(**stoch_orbit_kwargs))
    f = StochasticInvariantInducingPoints(idm.feature.Z.value)
    q_mu, q_var = idm.compute_qu()
    idsm = gpflow.models.SVGP(X, Y, k, gpflow.likelihoods.Gaussian(), f,
                              whiten=False,
                              q_mu=q_mu,
                              q_sqrt=np.linalg.cholesky(q_var)[None, :, :])  # inter-domain model
    idsm.likelihood.variance.assign(sig)

    # First check that the means are ok
    pred_idsm = np.mean([idsm.predict_f(Xt)[0] for _ in tqdm(range(samples))], 0)
    pred_idm = idm.predict_f(Xt)[0]
    pd = np.max(np.abs(pred_idm - pred_idsm) / pred_idm) * 100
    assert pd < 0.5

    # Next, check that the variational bound is unbiased

    lml_idm = idm.compute_log_likelihood()
    lml_idsm = np.mean([idsm.compute_log_likelihood() for _ in tqdm(range(lml_samples))])
    pd = np.max(np.abs(lml_idm - lml_idsm) / lml_idm) * 100
    assert pd < 0.5
