#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
import time
import zipfile

import jubilant
import pytest
from literals import BUNDLE_BUILD
from tests.integration.bundle.cos_helpers import deploy_cos_script
from tests.integration.bundle.multi_cloud import JujuTestbed

logger = logging.getLogger(__name__)


def pytest_addoption(parser):
    """Defines pytest parsers."""
    parser.addoption("--tls", action="store_true", help="set tls for e2e tests")

    parser.addoption(
        "--bundle-file",
        action="store",
        help="name of the bundle zip when provided.",
        default=BUNDLE_BUILD,
    )

    parser.addoption(
        "--model",
        action="store",
        help="Juju model to use; if not provided, a new model "
        "will be created for each test which requires one",
        default=None,
    )

    parser.addoption("--cos-model", action="store", help="COS model name", default="cos")

    parser.addoption(
        "--cos-channel", action="store", help="COS-lite bundle channel", default="edge"
    )


def pytest_generate_tests(metafunc):
    """Processes pytest parsers."""
    tls = metafunc.config.option.tls
    if "tls" in metafunc.fixturenames:
        metafunc.parametrize("tls", [bool(tls)], scope="module")

    bundle_file = metafunc.config.option.bundle_file
    if "bundle_file" in metafunc.fixturenames:
        metafunc.parametrize("bundle_file", [bundle_file], scope="module")

    model = metafunc.config.option.model
    if "model" in metafunc.fixturenames:
        metafunc.parametrize("model", [model], scope="module")


@pytest.fixture(scope="module")
def testbed(model: str, request: pytest.FixtureRequest):
    """Returns a JujuTestbed instance for handling multi-cloud deployments."""
    cos_model_name = f'{request.config.getoption("--cos-model")}'
    return JujuTestbed(model=model, cos_model=cos_model_name)


@pytest.fixture(scope="module")
def cos_overlay(bundle_file):
    with zipfile.ZipFile(bundle_file) as f:
        overlay = f.read("cos-overlay.yaml")
        fn = f"{os.path.dirname(bundle_file)}/test-cos-overlay.yaml"
        open(fn, "wb").write(overlay)
    return fn


@pytest.fixture(scope="module")
def lxd_controller(testbed: JujuTestbed):
    """Returns the VM controller name."""
    testbed.juju.model = f"{testbed.lxd_controller}:{testbed.model}"
    return testbed.lxd_controller


@pytest.fixture(scope="module")
def microk8s_controller(testbed: JujuTestbed, request: pytest.FixtureRequest):
    """Returns the microk8s controller name, boots up a new one if not existent."""
    if testbed.microk8s_controller:
        logger.info(f"Microk8s controller {testbed.microk8s_controller} exists, skipping setup...")
        return testbed.microk8s_controller

    testbed.bootstrap_microk8s()
    return "microk8s-localhost"


@pytest.fixture(scope="module")
def cos_lite(microk8s_controller: str, testbed: JujuTestbed, request: pytest.FixtureRequest):
    """Returns the COS-lite model, deploys a new one if not existent."""
    cos_model_name = testbed.cos_model
    cos_channel = f'{request.config.getoption("--cos-channel")}'

    model = testbed.get_model(microk8s_controller, cos_model_name)

    if model:
        yield
        return

    logger.info(f"Model {cos_model_name} doesn't exist, trying to deploy...")

    testbed.run_script(deploy_cos_script(microk8s_controller, cos_model_name, cos_channel))

    time.sleep(60)

    testbed.use_k8s()
    testbed.juju.wait(lambda status: jubilant.all_active(status), timeout=3000)
    yield
