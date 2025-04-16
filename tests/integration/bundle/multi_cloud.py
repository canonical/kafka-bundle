#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import glob
import json
import logging
import os
import secrets
from pathlib import Path
from subprocess import PIPE, check_output
from typing import Optional

import jubilant

logger = logging.getLogger(__name__)


class JujuTestbed:
    """Class for handling multi-cloud juju deployments."""

    def __init__(self, model: str | None = None, cos_model: str = "cos"):
        self.juju = jubilant.Juju()
        self.model = "jubilant-" + secrets.token_hex(4) if not model else model
        self.cos_model = cos_model

        self.get_or_create_model(self.lxd_controller, self.model)

    def _exec(self, cmd: str, cwd: str | None = None) -> str:
        """Executes a command on shell and returns the result."""
        return check_output(
            cmd,
            stderr=PIPE,
            shell=True,
            universal_newlines=True,
            cwd=cwd,
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

    def juju_cli(self, *args, json_output=True) -> dict:
        """Runs a juju command and returns the result in JSON format."""
        _format_json = [] if not json_output else ["--format", "json"]
        res = self.juju.cli(*args, *_format_json, include_model=False)

        if json_output:
            return json.loads(res)

        return {}

    def get_controller_name(self, cloud: str) -> Optional[str]:
        """Gets controller name for specified cloud, e.g. localhost, microk8s, lxd, etc."""
        res = self.juju_cli("controllers")
        for controller in res.get("controllers", {}):
            if res["controllers"][controller].get("cloud") == cloud:
                return controller

        return None

    def get_model(self, controller_name: str, model_name: str) -> str | None:
        """Gets a juju model on specified controller, and None if not found."""
        try:
            self.juju.add_model(model=model_name, controller=controller_name)
            return None
        except jubilant.CLIError:
            # model exists!
            return model_name

    def get_or_create_model(self, controller_name: str, model_name: str) -> str:
        """Returns an existing model on a controller or creates new one if not existing."""
        return self.juju.add_model(model=model_name, controller=controller_name)

    def bootstrap_microk8s(self) -> None:
        """Bootstrap juju on microk8s cloud."""
        user_env_var = os.environ.get("USER", "root")
        os.system("sudo apt install -y jq")
        ip_addr = self._exec("ip -4 -j route get 2.2.2.2 | jq -r '.[] | .prefsrc'").strip()

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

    def use_vm(self) -> None:
        """Use the VM controller for jubilant Juju."""
        self.juju.model = f"{self.lxd_controller}:{self.model}"
        self.juju_cli("switch", self.lxd_controller, json_output=False)

    def use_k8s(self) -> None:
        """Use the K8s controller for jubilant Juju."""
        self.juju.model = f"{self.microk8s_controller}:{self.cos_model}"
        self.juju_cli("switch", self.microk8s_controller, json_output=False)

    def build_charm(self, path: Path) -> str:
        # if we're in CI, no need to use charmcraft pack.
        if "CI" not in os.environ:
            for built_charm in glob.glob(f"{path}/*.charm"):
                self._exec(f"rm -rf {built_charm}")

            logger.info(f"Building {path}")
            self._exec("charmcraft pack", cwd=f"{path}")

        for built_path in glob.glob(f"{path}/*.charm"):
            return f"./{built_path}"

        raise Exception("Failed to build the charm.")

    @property
    def lxd_controller(self) -> Optional[str]:
        """Returns the lxd controller name or None if not available."""
        return self.get_controller_name("localhost")

    @property
    def microk8s_controller(self) -> Optional[str]:
        """Returns the microk8s controller name or None if not available."""
        return self.get_controller_name("microk8s")
