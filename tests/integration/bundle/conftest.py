#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
import zipfile

import pytest
from juju.errors import JujuConnectionError
from literals import BUNDLE_BUILD
from pytest_operator.plugin import OpsTest
from tests.integration.bundle.cos_helpers import deploy_cos_script
from tests.integration.bundle.multi_cloud import OpsTestbed

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


@pytest.fixture(scope="module")
def testbed(ops_test: OpsTest):
    """Returns an OpsTestbed instance for handling multi-cloud deployments."""
    return OpsTestbed(ops_test=ops_test)


@pytest.fixture(scope="module")
def cos_overlay(bundle_file, tmp_path_factory):
    with zipfile.ZipFile(bundle_file) as f:
        overlay = f.read("cos-overlay.yaml")
        fn = tmp_path_factory.mktemp("bundle") / "cos-overlay.yaml"
        open(fn, "wb").write(overlay)
    return fn


@pytest.fixture(scope="module")
async def lxd_controller(testbed: OpsTestbed):
    """Returns the VM controller name."""
    testbed.juju("switch", testbed.lxd_controller, json_output=False)
    await testbed.get_or_create_model(testbed.lxd_controller, testbed._ops_test.model.name)
    return testbed.lxd_controller


@pytest.fixture(scope="module")
def microk8s_controller(testbed: OpsTestbed):
    """Returns the microk8s controller name, boots up a new one if not existent."""
    if testbed.microk8s_controller:
        logger.info(f"Microk8s controller {testbed.microk8s_controller} exists, skipping setup...")
        return testbed.microk8s_controller

    testbed.bootstrap_microk8s()
    return "microk8s-localhost"


@pytest.fixture(scope="module")
async def cos_lite(microk8s_controller: str, testbed: OpsTestbed, request: pytest.FixtureRequest):
    """Returns the COS-lite model, deploys a new one if not existent."""
    cos_model_name = f'{request.config.getoption("--cos-model")}'
    cos_channel = f'{request.config.getoption("--cos-channel")}'

    try:
        model = await testbed.get_model(microk8s_controller, cos_model_name)
        yield model

        await model.disconnect()
        return
    except JujuConnectionError:
        logger.info(f"Model {cos_model_name} doesn't exist, trying to deploy...")

    testbed.run_script(deploy_cos_script(microk8s_controller, cos_model_name, cos_channel))

    await asyncio.sleep(60)
    model = await testbed.get_model(microk8s_controller, cos_model_name)

    await model.wait_for_idle(status="active", idle_period=60, timeout=3000, raise_on_error=False)
    yield model

    await model.disconnect()


@pytest.fixture(scope="module")
async def test_model(ops_test: OpsTest, testbed: OpsTestbed):
    """Returns the ops_test model on lxd cloud."""
    if not testbed.lxd_controller or not ops_test.model:
        raise Exception("Can't communicate with the controller.")

    model = await testbed.get_or_create_model(testbed.lxd_controller, ops_test.model.name)
    yield model

    await model.disconnect()
