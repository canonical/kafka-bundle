#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
import os
from subprocess import PIPE, check_output
from typing import Optional

from juju.errors import JujuConnectionError
from juju.model import Model
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


class OpsTestbed:
    """Fixture for handling multi-cloud juju deployments."""

    def __init__(self, ops_test: OpsTest):
        self._ops_test = ops_test
        logging.warning("When using Testbed, avoid interacting directly with ops_test.")
        pass

    def exec(self, cmd: str) -> str:
        """Executes a command on shell and returns the result."""
        return check_output(
            cmd,
            stderr=PIPE,
            shell=True,
            universal_newlines=True,
        )

    def run_script(self, script: str) -> None:
        """Runs a script on Linux OS.

        Args:
            script (str): Bash script

        Raises:
            OSError: If the script run fails.
        """
        for line in script.split("\n"):
            command = line.strip()

            if not command or command.startswith("#"):
                continue

            logger.info(command)
            ret_code = os.system(command)

            if ret_code:
                raise OSError(f'command "{command}" failed with error code {ret_code}')

    def juju(self, *args, json_output=True) -> dict:
        """Runs a juju command and returns the result in JSON format."""
        _format_json = "" if not json_output else "--format json"
        res = self.exec(f"juju {' '.join(args)} {_format_json}")

        if json_output:
            return json.loads(res)

        return {}

    def get_controller_name(self, cloud: str) -> Optional[str]:
        """Gets controller name for specified cloud, e.g. localhost, microk8s, lxd, etc."""
        res = self.juju("controllers")
        for controller in res.get("controllers", {}):
            if res["controllers"][controller].get("cloud") == cloud:
                return controller

        return None

    async def get_model(self, controller_name: str, model_name: str) -> Model:
        """Gets a juju model on specified controller, raises JujuConnectionError if not found."""
        state = await OpsTest._connect_to_model(controller_name, model_name)
        return state.model

    async def get_or_create_model(self, controller_name: str, model_name: str) -> Model:
        """Returns an existing model on a controller or creates new one if not existing."""
        try:
            return await self.get_model(controller_name, model_name)
        except JujuConnectionError:
            self.juju("add-model", "-c", controller_name, model_name, json_output=False)
            await asyncio.sleep(10)
            return await self.get_model(controller_name, model_name)

    def bootstrap_microk8s(self) -> None:
        """Bootstrap juju on microk8s cloud."""
        user_env_var = os.environ.get("USER", "root")
        os.system("sudo apt install -y jq")
        ip_addr = self.exec("ip -4 -j route get 2.2.2.2 | jq -r '.[] | .prefsrc'").strip()

        self.run_script(
            f"""
            # install microk8s
            sudo snap install microk8s --classic --channel=1.32

            # configure microk8s
            sudo usermod -a -G microk8s {user_env_var}
            mkdir -p ~/.kube
            chmod 0700 ~/.kube

            # ensure microk8s is up
            sudo microk8s status --wait-ready

            # enable required addons
            sudo microk8s enable dns
            sudo microk8s enable hostpath-storage
            sudo microk8s enable metallb:{ip_addr}-{ip_addr}

            # configure & bootstrap microk8s controller
            sudo mkdir -p /var/snap/juju/current/microk8s/credentials
            sudo microk8s config | sudo tee /var/snap/juju/current/microk8s/credentials/client.config
            sudo chown -R {user_env_var}:{user_env_var} /var/snap/juju/current/microk8s/credentials

            juju bootstrap microk8s
            sleep 90
        """
        )

    @property
    def lxd_controller(self) -> Optional[str]:
        """Returns the lxd controller name or None if not available."""
        return self.get_controller_name("localhost")

    @property
    def microk8s_controller(self) -> Optional[str]:
        """Returns the microk8s controller name or None if not available."""
        return self.get_controller_name("microk8s")
