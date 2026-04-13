#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import typing

import jubilant
import pytest
from tests.integration.terraform.component_validation import ComponentValidation
from tests.integration.terraform.helpers import (
    CA_FILE,
    CERTIFICATES_APP_NAME,
    COS_MODEL_NAME,
    TLS_MODEL_NAME,
    CosDeployer,
    MulticloudController,
    TerraformDeployer,
    all_active_idle,
    get_app_list,
    get_terraform_config,
)

KRaftMode = typing.Literal["single", "multi"]


def pytest_addoption(parser):
    """Defines pytest parsers."""
    parser.addoption(
        "--kraft-mode",
        action="store",
        help="KRaft mode to run the tests, 'single' or 'multi'",
        default="single",
    )
    parser.addoption(
        "--kafka-channel",
        action="store",
        help="Channel to use for the Kafka charm (broker and controller)",
        default="4/edge",
    )
    parser.addoption(
        "--cos-controller",
        action="store",
        help="Name of an existing Juju microk8s controller to deploy COS on. "
        "If not provided, a new microk8s controller will be bootstrapped.",
        default=None,
    )


@pytest.fixture(scope="module")
def kraft_mode(request: pytest.FixtureRequest) -> KRaftMode:
    """Returns the KRaft mode which is used to run the tests, should be either `single` or `multi`."""
    mode = f'{request.config.getoption("--kraft-mode")}' or "single"
    if mode not in ("single", "multi"):
        raise Exception("Unknown --kraft-mode, valid options are 'single' and 'multi'")

    return mode


@pytest.fixture(scope="module")
def kafka_channel(request: pytest.FixtureRequest) -> str:
    """Returns the Kafka charm channel to deploy."""
    return request.config.getoption("--kafka-channel") or "4/edge"


# -- Terraform --


@pytest.fixture()
def deploy_cluster(juju: jubilant.Juju, model_uuid: str, kraft_mode, kafka_channel):
    """Deploy the cluster in single mode."""
    terraform_deployer = TerraformDeployer(model_uuid)

    # Ensure cleanup of any previous state
    terraform_deployer.cleanup()

    config = get_terraform_config(split_mode=(kraft_mode == "multi"), kafka_channel=kafka_channel)
    tfvars_file = terraform_deployer.create_tfvars(config)

    terraform_deployer.terraform_init()
    terraform_deployer.terraform_apply(tfvars_file)


@pytest.fixture()
def enable_terraform_tls(juju: jubilant.Juju, model_uuid: str, kraft_mode, kafka_channel):
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
    tls_model.offer(f"{TLS_MODEL_NAME}.{CERTIFICATES_APP_NAME}", endpoint="certificates")

    # Store the CA cert for requests
    result = tls_model.run(f"{CERTIFICATES_APP_NAME}/0", "get-ca-certificate")
    ca = result.results.get("ca-certificate")
    open(CA_FILE, "w").write(ca)

    terraform_deployer = TerraformDeployer(model_uuid)
    config = get_terraform_config(
        enable_tls=True, split_mode=(kraft_mode == "multi"), kafka_channel=kafka_channel
    )
    tfvars_file = terraform_deployer.create_tfvars(config)
    terraform_deployer.terraform_apply(tfvars_file)


@pytest.fixture()
def disable_terraform_tls(juju: jubilant.Juju, model_uuid: str, kraft_mode):
    """Remove the tls endpoint and update terraform."""
    terraform_deployer = TerraformDeployer(model_uuid)
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


@pytest.fixture(scope="session")
def lxd_controller() -> typing.Optional[str]:
    """Return the name of the LXD (machines) Juju controller, or None if not found."""
    return MulticloudController().lxd_controller


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


@pytest.fixture(scope="module")
def model_uuid(juju: jubilant.Juju) -> str:
    return next(
        iter(
            mdl["model-uuid"]
            for mdl in json.loads(juju.cli("models", "--format", "json", include_model=False))[
                "models"
            ]
            if mdl["short-name"] == juju.model.split(":")[-1]
        )
    )


# -- COS --


@pytest.fixture(scope="module")
def cos_deployer(request: pytest.FixtureRequest):
    """Deploy COS-lite and yield the deployer. Destroys on teardown unless --keep-models."""
    # keep_models = typing.cast(bool, request.config.getoption("--keep-models"))
    k8s_controller = request.config.getoption("--cos-controller")
    deployer = CosDeployer(k8s_controller=k8s_controller)
    deployer.deploy()
    deployer.wait_for_active()
    yield deployer
    # if not keep_models:
    #     deployer.destroy()


@pytest.fixture(scope="module")
def cos_juju(cos_deployer: CosDeployer):
    """Return a Juju instance pointing at the COS model on the k8s controller."""
    k8s_controller = cos_deployer._resolved_k8s_controller
    return jubilant.Juju(model=f"{k8s_controller}:{COS_MODEL_NAME}")


@pytest.fixture(scope="module")
def deploy_cluster_with_cos(
    juju: jubilant.Juju,
    model_uuid: str,
    kraft_mode: KRaftMode,
    cos_deployer: CosDeployer,
):
    """Deploy the Kafka cluster with COS integration."""
    terraform_deployer = TerraformDeployer(model_uuid)
    terraform_deployer.cleanup()

    config = get_terraform_config(split_mode=(kraft_mode == "multi"))
    config["cos_offers"] = cos_deployer.get_cos_offers()
    tfvars_file = terraform_deployer.create_tfvars(config)

    terraform_deployer.terraform_init()
    terraform_deployer.terraform_apply(tfvars_file)


@pytest.fixture(autouse=True)
def service_logs(request, juju: jubilant.Juju):
    yield
    log_cmd = "tail -n 1000"
    if not request.session.testsfailed:
        return

    validator = ComponentValidation(juju=juju)
    for service, log_file in validator.service_logs.items():
        unit = getattr(validator, f"{service}_unit_name")
        print(f"{service} logs")
        print("##################################")
        print(juju.cli("ssh", unit, f"sudo {log_cmd} {log_file}"))
        print("##################################\n\n\n")
