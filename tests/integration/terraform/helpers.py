#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Terraform deployment helpers for integration tests."""

import json
import logging
import shutil
import socket
import subprocess
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, NamedTuple, Optional

import jubilant
import yaml

logger = logging.getLogger(__name__)


@dataclass
class Ports:
    """Types of ports for a Kafka broker."""

    client: int
    internal: int
    external: int
    controller: int
    extra: int = 0


AuthProtocol = Literal["SASL_PLAINTEXT", "SASL_SSL", "SSL"]
AuthMechanism = Literal["SCRAM-SHA-512", "OAUTHBEARER", "SSL"]
AuthMap = NamedTuple("AuthMap", protocol=AuthProtocol, mechanism=AuthMechanism)

SECURITY_PROTOCOL_PORTS: dict[AuthMap, Ports] = {
    AuthMap("SASL_PLAINTEXT", "SCRAM-SHA-512"): Ports(9092, 19092, 29092, 9097),
    AuthMap("SASL_SSL", "SCRAM-SHA-512"): Ports(9093, 19093, 29093, 9098),
    AuthMap("SSL", "SSL"): Ports(9094, 19094, 29094, 19194),
    AuthMap("SASL_PLAINTEXT", "OAUTHBEARER"): Ports(9095, 19095, 29095, 19195),
    AuthMap("SASL_SSL", "OAUTHBEARER"): Ports(9096, 19096, 29096, 19196),
}
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

KAFKA_UI_SECRET_KEY = "admin-password"


def all_active_idle(status: jubilant.Status, *apps: str):
    """Helper function for jubilant all units active|idle checks."""
    return jubilant.all_agents_idle(status, *apps) and jubilant.all_active(status, *apps)


def get_app_list(kraft_mode):
    """Get the list of expected applications based on kraft_mode."""
    base_apps = [KAFKA_UI_APP_NAME, KARAPACE_APP_NAME, CONNECT_APP_NAME, KAFKA_BROKER_APP_NAME]
    return base_apps + ([KAFKA_CONTROLLER_APP_NAME] if kraft_mode == "multi" else [])


class TerraformDeployer:
    """Helper class to manage Terraform deployments for testing."""

    def __init__(self, model_name: str, terraform_dir: str = "terraform"):
        self.model_name = model_name
        self.terraform_dir = Path(terraform_dir).resolve()
        self.tfvars_file = None

    def create_tfvars(self, config: Dict[str, Any]) -> str:
        """Create a .tfvars.json file with the given configuration."""
        self.tfvars_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".tfvars.json", delete=False
        )

        # Always include model
        config["model"] = self.model_name

        # Write JSON content
        json.dump(config, self.tfvars_file, indent=2)

        self.tfvars_file.close()
        return self.tfvars_file.name

    def get_controller_credentials(self) -> Dict[str, str]:
        """Get Juju controller credentials for Terraform."""
        controller_credentials = yaml.safe_load(
            subprocess.check_output(
                "juju show-controller --show-password",
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
        result = subprocess.run(
            ["terraform", "init"], cwd=self.terraform_dir, capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Terraform init failed: {result.stderr}")

        logger.info(f"\n\nTerraform initialized:\n\n{result.stdout}")

    def terraform_apply(self, tfvars_file: str):
        """Apply Terraform configuration."""
        env = self.get_controller_credentials()
        result = subprocess.run(
            ["terraform", "apply", "-auto-approve", f"-var-file={tfvars_file}"],
            cwd=self.terraform_dir,
            capture_output=True,
            text=True,
            env={**env, **dict(subprocess.os.environ)},
        )
        if result.returncode != 0:
            raise RuntimeError(f"Terraform apply failed: {result.stderr}")

        logger.info(f"\n\nTerraform applied:\n\n{result.stdout}")

    def terraform_destroy(self, tfvars_file: Optional[str] = None):
        """Destroy Terraform-managed resources."""
        env = self.get_controller_credentials()
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
    model_name: str,
    enable_cruise_control: bool = False,
    enable_tls: bool = False,
    split_mode: bool = False,
) -> Dict[str, Any]:
    """Get Terraform configuration based on deployment mode."""
    if split_mode:
        return get_multi_app_config(
            model_name=model_name,
            enable_cruise_control=enable_cruise_control,
            enable_tls=enable_tls,
        )
    else:
        return get_single_mode_config(
            model_name=model_name,
            enable_cruise_control=enable_cruise_control,
            enable_tls=enable_tls,
        )


def get_single_mode_config(
    model_name: str, enable_cruise_control: bool = False, enable_tls: bool = False
) -> Dict[str, Any]:
    """Get Terraform configuration for single-mode deployment."""
    config = {
        "profile": "testing",
        "broker": {
            "units": 1,
        },
        "connect": {"units": 1},
        "karapace": {"units": 1},
        "ui": {"units": 1},
        "integrator": {"units": 1},
    }
    if enable_tls:
        config = enable_tls_config(config, model_name)

    if enable_cruise_control:
        # Add balancer role while preserving existing roles
        config["broker"]["config"] = {"roles": "broker,balancer"}

    return config


def get_multi_app_config(
    model_name: str, enable_cruise_control: bool = False, enable_tls: bool = False
) -> Dict[str, Any]:
    """Get Terraform configuration for multi-app (split) mode deployment."""
    config = {
        "profile": "testing",
        "broker": {
            "units": 3,
        },
        "controller": {
            "units": 3,
        },
        "connect": {"units": 1},
        "karapace": {"units": 1},
        "ui": {"units": 1},
        "integrator": {"units": 1},
    }

    if enable_tls:
        config = enable_tls_config(config, model_name)

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
