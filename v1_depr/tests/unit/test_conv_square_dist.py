# Copyright (C) PROWLER.io 2018 - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential


import numpy as np
import tensorflow as tf
from numpy.testing import assert_allclose

from gpflow.kernels import RBF

from gpflux.conv_square_dists import (
    diag_conv_square_dist,
    full_conv_square_dist,
    image_patch_conv_square_dist,
    patchwise_conv_square_dist,
)
from gpflux.convolution.convolution_kernel import ConvKernel
from gpflux.utils import get_image_patches


class DT:
    N, H, W, C = image_shape = 9, 10, 10, 1
    M = 100
    h, w = filter_shape = 3, 3
    feat_size = M * h * w
    filter_size = h * w
    Ph, Pw = H - h + 1, W - w + 1
    P = Ph * Pw
    rng = np.random.RandomState(1010101)
    img1 = rng.randn(*image_shape)
    img2 = rng.randn(*image_shape)
    feat = rng.randn(M, h * w)

    image_shape = image_shape[1:]


def create_rbf(filter_size=None):
    k = RBF(filter_size or DT.filter_size)
    k.lengthscales = 0.2
    return k


def create_conv_kernel(image_shape=None, filter_size=None, colour_channels=1):
    rbf = create_rbf(filter_size)
    return ConvKernel(rbf, image_shape, filter_size, colour_channels=colour_channels)


def test_diag_conv_square_dist(session_tf):
    img = tf.convert_to_tensor(DT.img1)

    rbf = create_rbf()
    Xp = get_image_patches(img, DT.image_shape, DT.filter_shape)

    dist = diag_conv_square_dist(img, DT.filter_shape)
    dist /= rbf.lengthscales.constrained_tensor ** 2
    dist = tf.squeeze(dist)

    gotten = rbf.K_r2(dist)

    expect = rbf.K(Xp)

    gotten_np, expect_np = session_tf.run([gotten, expect])
    assert_allclose(expect_np, gotten_np)

    gotten_diag = tf.matrix_diag_part(rbf.K_r2(dist))
    expect_diag = rbf.Kdiag(Xp)

    gotten_diag_np, expect_diag_np = session_tf.run([gotten_diag, expect_diag])
    assert_allclose(expect_diag_np, gotten_diag_np)


def test_full_conv_square_dist(session_tf):
    rbf = create_rbf()
    N = DT.N
    P = DT.P
    img1 = tf.convert_to_tensor(DT.img1)
    img2 = tf.convert_to_tensor(DT.img2)

    X1 = get_image_patches(img1, DT.image_shape, DT.filter_shape)
    X2 = get_image_patches(img2, DT.image_shape, DT.filter_shape)
    X1 = tf.reshape(X1, (-1, DT.filter_size))
    X2 = tf.reshape(X2, (-1, DT.filter_size))

    expect = tf.reshape(rbf.K(X1, X2), (N, P, N, P))
    expect = tf.squeeze(expect)

    dist = full_conv_square_dist(img1, img2, DT.filter_shape)
    dist /= rbf.lengthscales.constrained_tensor ** 2
    dist = tf.squeeze(dist)
    gotten = rbf.K_r2(dist)

    gotten_np, expect_np = session_tf.run([gotten, expect])
    assert_allclose(expect_np, gotten_np)


def test_pairwise_conv_square_dist(session_tf):
    rbf = create_rbf()
    img1 = tf.convert_to_tensor(DT.img1)
    img2 = tf.convert_to_tensor(DT.img2)
    dtype = img1.dtype

    X1 = get_image_patches(img1, DT.image_shape, DT.filter_shape)
    X2 = get_image_patches(img2, DT.image_shape, DT.filter_shape)
    X1t = tf.transpose(X1, [1, 0, 2])
    X2t = tf.transpose(X2, [1, 0, 2])

    expect = tf.map_fn(lambda Xs: rbf.K(*Xs), (X1t, X2t), dtype=dtype)
    expect = tf.squeeze(expect)
    dist = patchwise_conv_square_dist(img1, img2, DT.filter_shape)
    dist /= rbf.lengthscales.constrained_tensor ** 2
    dist = tf.squeeze(dist)
    gotten = rbf.K_r2(dist)

    gotten_np, expect_np = session_tf.run([gotten, expect])
    assert_allclose(expect_np, gotten_np)

    expect = tf.map_fn(lambda x: rbf.K(x), X1t, dtype=dtype)
    dist = patchwise_conv_square_dist(img1, img1, DT.filter_shape)
    dist /= rbf.lengthscales.constrained_tensor ** 2
    dist = tf.squeeze(dist)
    gotten = rbf.K_r2(dist)

    gotten_np, expect_np = session_tf.run([gotten, expect])
    assert_allclose(expect_np, gotten_np)


def test_image_patch_conv_square_dist(session_tf):
    rbf = create_rbf()
    N = DT.N
    M, P = DT.M, DT.P
    X = tf.convert_to_tensor(DT.img1)
    Z = tf.convert_to_tensor(DT.feat)

    dist = image_patch_conv_square_dist(X, Z, DT.filter_shape)  # [N, M, P]
    dist /= rbf.lengthscales.constrained_tensor ** 2
    gotten = rbf.K_r2(dist)  # [N, M, P]
    gotten = tf.transpose(gotten, [1, 0, 2])

    Xp = get_image_patches(X, DT.image_shape, DT.filter_shape)
    expect = rbf.K(Z, tf.reshape(Xp, (N * P, -1)))
    expect = tf.reshape(expect, [M, N, P])

    gotten_np, expect_np = session_tf.run([gotten, expect])
    assert_allclose(expect_np, gotten_np)
