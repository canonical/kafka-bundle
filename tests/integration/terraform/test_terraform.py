#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import subprocess

import pytest
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


def get_value(obj: dict, key: str) -> list | str:
    """Recursively gets value for given key in nested dict."""
    if key in obj:
        return obj.get(key, "")

    for _, v in obj.items():
        if isinstance(v, dict):
            item = get_value(v, key)
            if item is not None:
                return item


@pytest.mark.abort_on_fail
async def test_deploy_terraform_active(ops_test: OpsTest):
    """Deploy using Terraform."""
    controller_credentials = yaml.safe_load(
        subprocess.check_output(
            "juju show-controller --show-password",
            stderr=subprocess.PIPE,
            shell=True,
            universal_newlines=True,
        )
    )

    username = get_value(obj=controller_credentials, key="user")
    password = get_value(obj=controller_credentials, key="password")
    controller_addresses = ",".join(get_value(obj=controller_credentials, key="api-endpoints"))
    ca_cert = get_value(obj=controller_credentials, key="ca-cert")

    print(ops_test.model_full_name)

    command = f"terraform init && terraform import juju_model.kafka {ops_test.model_name} && terraform apply -auto-approve -var 'model={ops_test.model_name}'"
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
    await ops_test.model.wait_for_idle(
        apps=["kafka", "zookeeper"], timeout=2000, idle_period=30, status="active"
    )
