# Copyright 2017 the GPflow authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import time
import traceback

import nbformat
import pytest
from nbconvert.preprocessors import ExecutePreprocessor
from nbconvert.preprocessors.execute import CellExecutionError

import gpflow

NOTEBOOK_FILES = [
    "deep_gp_samples.ipynb",
]

BLACKLISTED_NOTEBOOKS = [
    "conditional_deep_gp.ipynb",
    "deep_nonstationary_gp_samples.ipynb",
]


@pytest.mark.parametrize('notebook_file', NOTEBOOK_FILES)
@pytest.mark.skip('Skip until resolved why fails')
def test_notebook(notebook_file):
    gpflow.reset_default_graph_and_session()
    _exec_notebook_ts(notebook_file)


def test_no_notebook_missing():
    import glob
    all_notebooks = glob.glob(os.path.join(_nbpath(), '*.ipynb'))
    actual_notebook_files = set(map(os.path.basename, all_notebooks))
    assert set(NOTEBOOK_FILES) == actual_notebook_files - set(BLACKLISTED_NOTEBOOKS)


def _nbpath():
    this_dir = os.path.dirname(__file__)
    return os.path.join(this_dir, '../../notebooks/')


def _preproc():
    pythonkernel = 'python' + str(sys.version_info[0])
    return ExecutePreprocessor(timeout=300, kernel_name=pythonkernel,
                               interrupt_on_timeout=True)


def _exec_notebook(notebook_filename):
    full_notebook_filename = os.path.join(_nbpath(), notebook_filename)
    with open(full_notebook_filename) as notebook_file:
        nb = nbformat.read(notebook_file, as_version=nbformat.current_nbformat)
        try:
            _preproc().preprocess(nb, {'metadata': {'path': _nbpath()}})
        except CellExecutionError as cell_error:
            traceback.print_exc(file=sys.stdout)
            msg = 'Error executing the notebook {0}. See above for error.\nCell error: {1}'
            pytest.fail(msg.format(notebook_filename, str(cell_error)))


def _exec_notebook_ts(notebook_filename):
    ts = time.time()
    _exec_notebook(notebook_filename)
    elapsed = time.time() - ts
    print(notebook_filename, 'took {0} seconds.'.format(elapsed))
