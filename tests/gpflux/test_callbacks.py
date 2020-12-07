from collections import defaultdict
from typing import Tuple

import numpy as np
import pytest
import tensorflow as tf

import gpflow

import gpflux
from gpflux.helpers import construct_gp_layer
from gpflux.utils.tensorboard import tensorboard_event_iterator


class CONFIG:
    hidden_dim = 11
    num_inducing = 13
    num_data = 7
    num_epochs = 29

    # model setting:
    likelihood_variance = 0.05


@pytest.fixture
def data() -> Tuple[np.ndarray, np.ndarray]:
    """Step function: f(x) = -1 for x <=0; elif 1 for x > 0."""
    X = np.linspace(-1, 1, CONFIG.num_data)
    Y = np.where(X > 0, np.ones_like(X), -1.0 * np.ones_like(X))
    return (X.reshape(-1, 1), Y.reshape(-1, 1))


@pytest.fixture
def model(data) -> tf.keras.models.Model:
    """
    Builds a two-layer deep GP model.
    """
    X, Y = data
    num_data, input_dim = X.shape

    layer1 = construct_gp_layer(num_data, CONFIG.num_inducing, input_dim, CONFIG.hidden_dim)
    layer1.returns_samples = True

    output_dim = Y.shape[-1]
    layer2 = construct_gp_layer(num_data, CONFIG.num_inducing, CONFIG.hidden_dim, output_dim)
    layer2.returns_samples = False

    likelihood_layer = gpflux.layers.LikelihoodLayer(
        gpflow.likelihoods.Gaussian(CONFIG.likelihood_variance)
    )
    gpflow.set_trainable(likelihood_layer.likelihood.variance, False)

    X = tf.keras.Input((input_dim,))
    f1 = layer1(X)
    f2 = layer2(f1)
    y = likelihood_layer(f2, targets=Y)
    return tf.keras.Model(inputs=X, outputs=y)


@pytest.mark.parametrize("update_freq", ["epoch", "batch"])
def test_tensorboard_callback(tmp_path, model, data, update_freq):
    """Check the correct population of the TensorBoard event files"""

    tmp_path = str(tmp_path)
    dataset = tf.data.Dataset.from_tensor_slices(data).batch(CONFIG.num_data)
    optimizer = tf.keras.optimizers.Adam(learning_rate=1e-2)
    model.compile(optimizer=optimizer)
    callbacks = [
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="loss", patience=1, factor=0.95, verbose=1, min_lr=1e-6,
        ),
        # To write the LR to TensorBoard the `TensorBoard` callback needs to be
        # instantiated after the `ReduceLROnPlateau` callback.
        gpflux.callbacks.TensorBoard(tmp_path, update_freq=update_freq),
    ]
    history = model.fit(dataset, epochs=CONFIG.num_epochs, callbacks=callbacks)

    tb_files_pattern = f"{tmp_path}/train/events.out.tfevents*"  # notice the glob pattern

    # Maps tensorboard tags (e.g. kernel.variance) to list containing
    # their successive values during optimisation.
    records = defaultdict(list)  # Dict[str, list]

    # Loop over all events and add them to dict
    for event in tensorboard_event_iterator(tb_files_pattern):
        records[event.tag].append(event.value)

    # Keras adds a single event of `batch_2`, which we ignore.
    # It's not visible in the TensorBoard view, but it is in the event file.
    del records["batch_2"]

    expected_tags = {
        # TODO(VD) investigate why epoch_lr is not in tensorboard files
        # "epoch_lr",
        "epoch_loss",
        "epoch_elbo_datafit",
        "epoch_elbo_kl_gp",
        "layers[1].kernel.kernel.lengthscales",
        "layers[1].kernel.kernel.variance",
        "layers[2].kernel.kernel.lengthscales[0]",
        "layers[2].kernel.kernel.lengthscales[1]",
        "layers[2].kernel.kernel.lengthscales[2]",
        "layers[2].kernel.kernel.variance",
        "layers[3].likelihood.variance",
    }

    if update_freq == "batch":
        expected_tags |= {
            "batch_loss",
            "batch_elbo_datafit",
            "batch_elbo_kl_gp",
        }

    # Check all model variables, loss and lr are in tensorboard.
    assert set(records.keys()) == expected_tags

    # Check that length of each summary is correct.
    for record in records.values():
        assert len(record) == CONFIG.num_epochs

    # Check that recorded TensorBoard loss matches Keras history
    np.testing.assert_array_almost_equal(records["epoch_loss"], history.history["loss"], decimal=5)

    # Check correctness of fixed likelihood variance
    tag = ("layers[3].likelihood.variance",)
    assert all([v == CONFIG.likelihood_variance for v in records[tag]])
