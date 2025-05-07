#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import subprocess
from typing import Generator

import jubilant
import pytest
import yaml

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest) -> Generator[jubilant.Juju, None, None]:
    """Pytest fixture that wraps :meth:`jubilant.with_model`."""
    with jubilant.temp_model(keep=True) as juju:
        yield juju

        if request.session.testsfailed:
            log = juju.debug_log(limit=1000)
            print(log, end="")


def get_value(obj: dict, key: str) -> list | str:
    """Recursively gets value for given key in nested dict."""
    if key in obj:
        return obj.get(key, "")

    for _, v in obj.items():
        if isinstance(v, dict):
            item = get_value(v, key)
            if item is not None:
                return item


def test_deploy_terraform_active(juju):
    """Deploy using Terraform."""
    controller_credentials = yaml.safe_load(
        juju.cli("show-controller", "--show-password", include_model=False)
    )

    username = get_value(obj=controller_credentials, key="user")
    password = get_value(obj=controller_credentials, key="password")
    controller_addresses = ",".join(get_value(obj=controller_credentials, key="api-endpoints"))
    ca_cert = get_value(obj=controller_credentials, key="ca-cert")

    command = f"terraform init && terraform import juju_model.kafka {juju.model} && terraform apply -auto-approve -var 'model={juju.model}'"

    try:
        subprocess.check_output(
            command,
            stderr=subprocess.PIPE,
            shell=True,
            universal_newlines=True,
            cwd="terraform/dev",
            env={
                "JUJU_CONTROLLER_ADDRESSES": str(controller_addresses),
                "JUJU_USERNAME": str(username),
                "JUJU_PASSWORD": str(password),
                "JUJU_CA_CERT": str(ca_cert),
            },
        )
    except subprocess.CalledProcessError as e:
        logger.info(e.output)
        logger.info(e.stdout)
        logger.info(e.stderr)
        raise e

    juju.wait(
        lambda status: jubilant.all_active(status, "kafka", "zookeeper"),
        timeout=2000,
        delay=10,
    )
