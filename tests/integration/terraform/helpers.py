#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Terraform deployment helpers for integration tests."""

import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Optional

import jubilant
import yaml

logger = logging.getLogger(__name__)


KAFKA_INTERNAL_PORT = 19093
KARAPACE_PORT = 8081
KAFKA_UI_PORT = 8080
KAFKA_UI_PROTO = "https"
CONNECT_API_PORT = 8083

CONNECT_APP_NAME = "kafka-connect"
KARAPACE_APP_NAME = "karapace"
KAFKA_UI_APP_NAME = "kafka-ui"
KAFKA_BROKER_APP_NAME = "kafka-broker"
KAFKA_CONTROLLER_APP_NAME = "kafka-controller"

CERTIFICATES_APP_NAME = "self-signed-certificates"
TLS_MODEL_NAME = "tls-model"
TLS_RELATION_OFFER = f"admin/{TLS_MODEL_NAME}.{CERTIFICATES_APP_NAME}"
CA_FILE = "/tmp/ca.pem"
COS_MODEL_NAME = "test-cos"
COS_TERRAFORM_DIR = "tests/integration/terraform/cos"

KAFKA_UI_SECRET_KEY = "admin-password"

# Base Terraform configs
SINGLE_MODE_DEFAULT_CONFIG = {
    "profile": "testing",
    "broker": {"units": 1},
    "connect": {"units": 1},
    "karapace": {"units": 1},
    "ui": {"units": 1},
    "integrator": {"units": 1},
}
SPLIT_MODE_DEFAULT_CONFIG = {
    "profile": "testing",
    "broker": {"units": 3},
    "controller": {"units": 3},
    "connect": {"units": 1},
    "karapace": {"units": 1},
    "ui": {"units": 1},
    "integrator": {"units": 1},
}


class TerraformDeployer:
    """Helper class to manage Terraform deployments for testing."""

    def __init__(
        self, model_uuid: str, terraform_dir: str = "terraform", controller: Optional[str] = None
    ):
        self.model_uuid = model_uuid
        self.terraform_dir = Path(terraform_dir).resolve()
        self.tfvars_file = None
        self._controller = controller

    def create_tfvars(self, config: Dict[str, Any]) -> str:
        """Create a .tfvars.json file with the given configuration."""
        self.tfvars_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".tfvars.json", delete=False
        )

        # Always include model
        config["model_uuid"] = self.model_uuid

        # Write JSON content
        json.dump(config, self.tfvars_file, indent=2)

        self.tfvars_file.close()
        return self.tfvars_file.name

    def get_controller_credentials(self, controller: Optional[str] = None) -> Dict[str, str]:
        """Get Juju controller credentials for Terraform.

        Args:
            controller: If provided, fetch credentials for this named controller.
                        Otherwise, uses the currently active controller.
        """
        cmd = "juju show-controller --show-password"
        if controller:
            cmd = f"juju show-controller {controller} --show-password"
        controller_credentials = yaml.safe_load(
            subprocess.check_output(
                cmd,
                stderr=subprocess.PIPE,
                shell=True,
                universal_newlines=True,
            )
        )

        def get_value(obj: dict, key: str):
            """Recursively gets value for given key in nested dict."""
            if key in obj:
                return obj.get(key, "")
            for _, v in obj.items():
                if isinstance(v, dict):
                    item = get_value(v, key)
                    if item is not None:
                        return item

        username = get_value(obj=controller_credentials, key="user")
        password = get_value(obj=controller_credentials, key="password")
        controller_addresses = ",".join(get_value(obj=controller_credentials, key="api-endpoints"))
        ca_cert = get_value(obj=controller_credentials, key="ca-cert")

        return {
            "JUJU_USERNAME": username,
            "JUJU_PASSWORD": password,
            "JUJU_CONTROLLER_ADDRESSES": controller_addresses,
            "JUJU_CA_CERT": ca_cert,
        }

    def terraform_init(self):
        """Initialize Terraform in the terraform directory."""
        result = subprocess.run(["terraform", "init"], cwd=self.terraform_dir, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Terraform init failed: {result.stderr}")

        logger.info(f"\n\nTerraform initialized:\n\n{result.stdout}")

    def terraform_apply(self, tfvars_file: str):
        """Apply Terraform configuration."""
        env = self.get_controller_credentials(self._controller)
        result = subprocess.run(
            ["terraform", "apply", "-auto-approve", f"-var-file={tfvars_file}"],
            cwd=self.terraform_dir,
            text=True,
            env={**env, **dict(subprocess.os.environ)},
        )
        if result.returncode != 0:
            raise RuntimeError(f"Terraform apply failed: {result.stderr}")

        logger.info(f"\n\nTerraform applied:\n\n{result.stdout}")

    def terraform_destroy(self, tfvars_file: Optional[str] = None):
        """Destroy Terraform-managed resources."""
        env = self.get_controller_credentials(self._controller)
        cmd = ["terraform", "destroy", "-auto-approve"]
        if tfvars_file:
            cmd.append(f"-var-file={tfvars_file}")

        result = subprocess.run(
            cmd,
            cwd=self.terraform_dir,
            capture_output=True,
            text=True,
            env={**env, **dict(subprocess.os.environ)},
        )
        if result.returncode != 0:
            raise RuntimeError(f"Terraform destroy failed: {result.stderr}")

    def terraform_output(self) -> Dict[str, Any]:
        """Read terraform output as a JSON dict."""
        env = self.get_controller_credentials(self._controller)
        result = subprocess.check_output(
            ["terraform", "output", "-json"],
            cwd=self.terraform_dir,
            text=True,
            env={**env, **dict(subprocess.os.environ)},
        )
        return json.loads(result)

    def cleanup(self):
        """Clean up temporary files."""
        if self.tfvars_file and Path(self.tfvars_file.name).exists():
            Path(self.tfvars_file.name).unlink()

        # Clean up terraform artifacts
        shutil.rmtree(self.terraform_dir / ".terraform", ignore_errors=True)
        for pattern in [".terraform.lock.hcl", "terraform.tfstate*", "*.tfplan"]:
            for file_path in self.terraform_dir.glob(pattern):
                file_path.unlink(missing_ok=True)


def get_terraform_config(
    enable_cruise_control: bool = False,
    enable_tls: bool = False,
    split_mode: bool = False,
    kafka_channel: str = "4/edge",
) -> Dict[str, Any]:
    """Get Terraform configuration based on deployment mode."""
    if split_mode:
        return get_multi_app_config(
            enable_cruise_control=enable_cruise_control,
            enable_tls=enable_tls,
            kafka_channel=kafka_channel,
        )
    else:
        return get_single_mode_config(
            enable_cruise_control=enable_cruise_control,
            enable_tls=enable_tls,
            kafka_channel=kafka_channel,
        )


def get_single_mode_config(
    enable_cruise_control: bool = False, enable_tls: bool = False, kafka_channel: str = "4/edge"
) -> Dict[str, Any]:
    """Get Terraform configuration for single-mode deployment."""
    config = SINGLE_MODE_DEFAULT_CONFIG.copy()
    config["broker"] = {**config["broker"], "channel": kafka_channel}
    if enable_tls:
        config = enable_tls_config(config)

    if enable_cruise_control:
        # Add balancer role while preserving existing roles
        config["broker"]["config"] = {"roles": "broker,balancer"}

    return config


def get_multi_app_config(
    enable_cruise_control: bool = False, enable_tls: bool = False, kafka_channel: str = "4/edge"
) -> Dict[str, Any]:
    """Get Terraform configuration for multi-app (split) mode deployment."""
    config = SPLIT_MODE_DEFAULT_CONFIG.copy()
    config["broker"] = {**config["broker"], "channel": kafka_channel}
    config["controller"] = {**config["controller"], "channel": kafka_channel}

    if enable_tls:
        config = enable_tls_config(config)

    if enable_cruise_control:
        # Add balancer role while preserving existing roles
        config["broker"]["config"] = {"roles": "broker,balancer"}

    return config


def enable_tls_config(base_config: Dict[str, Any]) -> Dict[str, Any]:
    """Modify configuration to enable TLS across all components."""
    tls_config = base_config.copy()

    # For TLS testing, we'll need to add TLS offer
    # This would typically come from a TLS certificates operator
    tls_config["tls_offer"] = TLS_RELATION_OFFER

    return tls_config


def get_secret_by_label(model: str, label: str, owner: str) -> dict[str, str]:
    secrets_meta_raw = subprocess.check_output(
        f"JUJU_MODEL={model} juju list-secrets --format json",
        stderr=subprocess.PIPE,
        shell=True,
        universal_newlines=True,
    ).strip()
    secrets_meta = json.loads(secrets_meta_raw)

    for secret_id in secrets_meta:
        if owner and not secrets_meta[secret_id]["owner"] == owner:
            continue
        if secrets_meta[secret_id]["label"] == label:
            break

    secrets_data_raw = subprocess.check_output(
        f"JUJU_MODEL={model} juju show-secret --format json --reveal {secret_id}",
        stderr=subprocess.PIPE,
        shell=True,
        universal_newlines=True,
    )

    secret_data = json.loads(secrets_data_raw)
    return secret_data[secret_id]["content"]["Data"]


def check_socket(host: str | None, port: int) -> bool:
    """Checks whether IPv4 socket is up or not."""
    if host is None:
        return False

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        return sock.connect_ex((host, port)) == 0


def all_active_idle(status: jubilant.Status, *apps: str):
    """Helper function for jubilant all units active|idle checks."""
    return jubilant.all_agents_idle(status, *apps) and jubilant.all_active(status, *apps)


def get_app_list(kraft_mode):
    """Get the list of expected applications based on kraft_mode."""
    base_apps = [KAFKA_UI_APP_NAME, KARAPACE_APP_NAME, CONNECT_APP_NAME, KAFKA_BROKER_APP_NAME]
    return base_apps + ([KAFKA_CONTROLLER_APP_NAME] if kraft_mode == "multi" else [])


class MulticloudController:
    """Helper for managing multi-cloud Juju deployments (LXD + MicroK8s)."""

    def _exec(self, cmd: str) -> str:
        """Execute a shell command and return stdout."""
        return subprocess.check_output(
            cmd, stderr=subprocess.PIPE, shell=True, universal_newlines=True
        )

    def run_script(self, script: str) -> None:
        """Run a multi-line bash script, line by line."""
        for line in script.split("\n"):
            command = line.strip()
            if not command or command.startswith("#"):
                continue
            logger.info(command)
            ret_code = os.system(command)
            if ret_code:
                raise OSError(f'command "{command}" failed with error code {ret_code}')

    def juju_json(self, *args) -> dict:
        """Run a juju command and return parsed JSON output."""
        res = self._exec(f"juju {' '.join(args)} --format json")
        return json.loads(res)

    def get_controller_name(self, cloud: str) -> Optional[str]:
        """Return the name of the controller registered for a given cloud type."""
        res = self.juju_json("controllers")
        for controller, info in res.get("controllers", {}).items():
            if info.get("cloud") == cloud:
                return controller
        return None

    @property
    def lxd_controller(self) -> Optional[str]:
        """Return the LXD controller name, or None if not found."""
        return self.get_controller_name("localhost")

    @property
    def microk8s_controller(self) -> Optional[str]:
        """Return the microk8s controller name, or None if not found."""
        return self.get_controller_name("microk8s")

    def bootstrap_microk8s(self) -> None:
        """Install microk8s and bootstrap a Juju controller on it."""
        user = os.environ.get("USER", "root")
        ip_addr = self._exec("ip -4 -j route get 2.2.2.2 | jq -r '.[] | .prefsrc'").strip()

        self.run_script(
            f"""
            # install microk8s
            sudo snap install microk8s --classic --channel=1.32

            # configure microk8s user/group
            sudo usermod -a -G microk8s {user}
            mkdir -p ~/.kube
            chmod 0700 ~/.kube

            # wait for microk8s
            sudo microk8s status --wait-ready

            # enable required addons
            sudo microk8s enable dns
            sudo microk8s enable hostpath-storage
            sudo microk8s enable metallb:{ip_addr}-{ip_addr}

            # configure kubeconfig for juju
            sudo mkdir -p /var/snap/juju/current/microk8s/credentials
            sudo microk8s config | sudo tee /var/snap/juju/current/microk8s/credentials/client.config
            sudo chown -R {user}:{user} /var/snap/juju/current/microk8s/credentials

            juju bootstrap microk8s
            sleep 90
        """
        )

    def ensure_microk8s_controller(self) -> str:
        """Return existing microk8s controller name, or bootstrap one if missing."""
        controller = self.microk8s_controller
        if controller:
            logger.info(f"Microk8s controller '{controller}' already exists, skipping bootstrap.")
            return controller
        logger.info("No microk8s controller found, bootstrapping...")
        self.bootstrap_microk8s()
        controller = self.microk8s_controller
        if not controller:
            raise RuntimeError("Failed to bootstrap microk8s controller")
        return controller


class COS:
    """COS application name constants."""

    ALERTMANAGER = "alertmanager"
    CATALOGUE = "catalogue"
    TRAEFIK = "traefik"
    GRAFANA = "grafana"
    LOKI = "loki"
    PROMETHEUS = "prometheus"

    APPS = [ALERTMANAGER, CATALOGUE, GRAFANA, LOKI, PROMETHEUS, TRAEFIK]


class COSAssertions:
    """Expected values for COS integration assertions."""

    APP = "kafka"
    DASHBOARDS = ["Kafka", "Kafka Connect Cluster"]
    PANELS_COUNT = 50
    PANELS_TO_CHECK = (
        "JVM",
        "Brokers Online",
        "Active Controllers",
        "Total of Topics",
    )
    ALERTS_COUNT_SINGLE = 25
    ALERTS_COUNT_MULTI = 45


class CosDeployer:
    """Helper class to manage COS-lite deployment for integration tests.

    Deploys COS-lite on a separate microk8s Juju controller (cross-controller)
    """

    def __init__(self, k8s_controller: Optional[str] = None):
        self.cos_juju: Optional[jubilant.Juju] = None
        self.deployer: Optional[TerraformDeployer] = None
        self._multicloud = MulticloudController()
        self._k8s_controller: Optional[str] = k8s_controller

    def _get_k8s_controller(self) -> str:
        """Return the k8s controller to use, bootstrapping microk8s if needed."""
        if self._k8s_controller:
            return self._k8s_controller
        return self._multicloud.ensure_microk8s_controller()

    def deploy(self, channel: str = "dev/edge") -> None:
        """Deploy COS-lite in a separate microk8s Juju model via Terraform."""
        k8s_controller = self._get_k8s_controller()
        self._resolved_k8s_controller = k8s_controller
        logger.info(f"Deploying COS-lite on k8s controller '{k8s_controller}'")

        # Create the COS model on the k8s controller explicitly (no juju switch needed).
        # Use controller:model prefix so jubilant targets the right controller without switching.
        jubilant.Juju().cli("add-model", "--controller", k8s_controller, COS_MODEL_NAME)
        self.cos_juju = jubilant.Juju(model=f"{k8s_controller}:{COS_MODEL_NAME}")

        # Resolve model UUID by querying the k8s controller directly
        models_raw = subprocess.check_output(
            ["juju", "models", "--controller", k8s_controller, "--format", "json"],
            text=True,
        )
        models = json.loads(models_raw)
        cos_model_uuid = next(
            mdl["model-uuid"] for mdl in models["models"] if mdl["short-name"] == COS_MODEL_NAME
        )

        self.deployer = TerraformDeployer(
            cos_model_uuid, COS_TERRAFORM_DIR, controller=k8s_controller
        )
        self.deployer.cleanup()

        config = {"channel": channel}
        tfvars_file = self.deployer.create_tfvars(config)

        self.deployer.terraform_init()
        self.deployer.terraform_apply(tfvars_file)

    def get_cos_offers(self) -> Dict[str, str]:
        """Get COS offer URLs mapped to Kafka bundle cos_offers keys."""
        output = self.deployer.terraform_output()
        offers = output["offers"]["value"]
        return {
            "dashboard": offers["grafana_dashboards"]["url"],
            "metrics": offers["prometheus_metrics"]["url"],
            "logging": offers["loki_logging"]["url"],
        }

    def wait_for_active(self, timeout: int = 1800) -> None:
        """Wait for all COS apps to be active/idle."""
        self.cos_juju.wait(
            lambda status: all_active_idle(status, *COS.APPS),
            delay=5,
            successes=5,
            timeout=timeout,
        )

    def destroy(self) -> None:
        """Destroy COS deployment: terraform destroy first, then remove the model."""
        if self.deployer:
            try:
                self.deployer.terraform_destroy(
                    tfvars_file=self.deployer.tfvars_file.name
                    if self.deployer.tfvars_file
                    else None
                )
            except RuntimeError:
                logger.warning("Terraform destroy failed, proceeding with model removal")
            self.deployer.cleanup()

        k8s_controller = getattr(self, "_resolved_k8s_controller", None) or self._k8s_controller
        try:
            destroy_cmd = ["juju", "destroy-model", "--no-prompt", "--force", COS_MODEL_NAME]
            if k8s_controller:
                destroy_cmd += ["--controller", k8s_controller]
            subprocess.run(destroy_cmd, check=True)
        except Exception:
            logger.warning(f"Failed to destroy model {COS_MODEL_NAME}")
