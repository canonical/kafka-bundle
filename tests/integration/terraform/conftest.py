#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import typing

import jubilant
import pytest
from tests.integration.terraform.helpers import (
    CA_FILE,
    CERTIFICATES_APP_NAME,
    TLS_MODEL_NAME,
    TerraformDeployer,
    all_active_idle,
    get_app_list,
    get_terraform_config,
)

KRaftMode = typing.Literal["single", "multi"]


def pytest_addoption(parser):
    """Defines pytest parsers."""
    parser.addoption(
        "--kraft-mode", action="store", help="KRaft mode to run the tests", default="single"
    )


@pytest.fixture(scope="module")
def kraft_mode(request: pytest.FixtureRequest) -> KRaftMode:
    """Returns the KRaft mode which is used to run the tests, should be either `single` or `multi`."""
    mode = f'{request.config.getoption("--kraft-mode")}' or "single"
    if mode not in ("single", "multi"):
        raise Exception("Unknown --kraft-mode, valid options are 'single' and 'multi'")

    return mode


# -- Terraform --


@pytest.fixture()
def deploy_cluster(juju: jubilant.Juju, kraft_mode):
    """Deploy the cluster in single mode."""
    terraform_deployer = TerraformDeployer(juju.model)

    # Ensure cleanup of any previous state
    terraform_deployer.cleanup()

    config = get_terraform_config(split_mode=(kraft_mode == "multi"))
    tfvars_file = terraform_deployer.create_tfvars(config)

    terraform_deployer.terraform_init()
    terraform_deployer.terraform_apply(tfvars_file)


@pytest.fixture()
def enable_terraform_tls(juju: jubilant.Juju, kraft_mode):
    """Deploy a tls endpoint and update terraform."""
    jubilant.Juju().add_model(model=TLS_MODEL_NAME)
    tls_model = jubilant.Juju(model=TLS_MODEL_NAME)
    tls_model.deploy(CERTIFICATES_APP_NAME, config={"ca-common-name": "test-ca"}, channel="stable")
    tls_model.wait(
        lambda status: all_active_idle(status, CERTIFICATES_APP_NAME),
        delay=5,
        successes=5,
        timeout=600,
    )
    tls_model.offer(CERTIFICATES_APP_NAME, endpoint="certificates")

    # Store the CA cert for requests
    result = tls_model.run(f"{CERTIFICATES_APP_NAME}/0", "get-ca-certificate")
    ca = result.results.get("ca-certificate")
    open(CA_FILE, "w").write(ca)

    terraform_deployer = TerraformDeployer(juju.model)
    config = get_terraform_config(enable_tls=True, split_mode=(kraft_mode == "multi"))
    tfvars_file = terraform_deployer.create_tfvars(config)
    terraform_deployer.terraform_apply(tfvars_file)


@pytest.fixture()
def disable_terraform_tls(juju: jubilant.Juju, kraft_mode):
    """Remove the tls endpoint and update terraform."""
    terraform_deployer = TerraformDeployer(juju.model)
    config = get_terraform_config(enable_tls=False, split_mode=(kraft_mode == "multi"))
    tfvars_file = terraform_deployer.create_tfvars(config)

    terraform_deployer.terraform_apply(tfvars_file)

    juju.wait(
        lambda status: all_active_idle(status, *get_app_list(kraft_mode)),
        delay=5,
        successes=6,
        timeout=1800,
    )

    juju.destroy_model(model=TLS_MODEL_NAME, force=True)


# -- Jubilant --


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest):
    model = request.config.getoption("--model")
    keep_models = typing.cast(bool, request.config.getoption("--keep-models"))

    if model is None:
        with jubilant.temp_model(keep=keep_models) as juju:
            juju.wait_timeout = 10 * 60
            juju.model_config({"update-status-hook-interval": "180s"})
            yield juju

            log = juju.debug_log(limit=1000)
    else:
        juju = jubilant.Juju(model=model)
        yield juju
        log = juju.debug_log(limit=1000)

    if request.session.testsfailed:
        print(log, end="")
