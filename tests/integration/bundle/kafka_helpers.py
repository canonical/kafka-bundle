#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import json
import logging
import re
from subprocess import PIPE, CalledProcessError, check_output
from typing import Any, Dict, List, Set, Tuple

import yaml
from pytest_operator.plugin import OpsTest
from tests.integration.bundle.literals import KAFKA_CLIENT_PROPERTIES, ZOOKEEPER_CONF_PATH

from .auth import Acl, KafkaAuth

logger = logging.getLogger(__name__)


def load_acls(model_full_name: str, bootstrap_server: str, unit_name: str) -> Set[Acl]:
    command = f"JUJU_MODEL={model_full_name} juju ssh {unit_name} sudo -i 'charmed-kafka.acls --bootstrap-server {bootstrap_server} --command-config {KAFKA_CLIENT_PROPERTIES} --list'"
    try:
        result = check_output(
            command,
            stderr=PIPE,
            shell=True,
            universal_newlines=True,
        )
        return KafkaAuth._parse_acls(acls=result)
    except CalledProcessError as e:
        logger.error(f"{str(e.stdout)=}")
        raise e


def load_super_users(model_full_name: str, unit_name: str) -> List[str]:
    if "k8s" in unit_name:
        command = (
            f"JUJU_MODEL={model_full_name} juju ssh --container kafka {unit_name} 'cat /data/kafka/config/server.properties'",
        )
    else:
        command = (
            f"JUJU_MODEL={model_full_name} juju ssh {unit_name} 'cat /var/snap/kafka/common/server.properties'",
        )

    result = check_output(
        command,
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    )
    properties = result.splitlines()

    for prop in properties:
        if "super.users" in prop:
            return prop.split("=")[1].split(";")

    return []


def check_user(model_full_name: str, username: str, bootstrap_server: str, unit_name: str) -> None:
    command = f"JUJU_MODEL={model_full_name} juju ssh {unit_name} sudo -i 'charmed-kafka.configs --bootstrap-server {bootstrap_server} --command-config {KAFKA_CLIENT_PROPERTIES} --describe --entity-type users --entity-name {username}'"
    try:
        result = check_output(
            command,
            stderr=PIPE,
            shell=True,
            universal_newlines=True,
        )
        assert "SCRAM-SHA-512" in result
    except CalledProcessError as e:
        logger.error(f"{str(e.stdout)=}")
        raise e


def show_unit(unit_name: str, model_full_name: str) -> Any:
    result = check_output(
        f"JUJU_MODEL={model_full_name} juju show-unit {unit_name}",
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    )

    return yaml.safe_load(result)


def get_secret_by_label(model_full_name: str, label: str, owner: str) -> dict[str, str]:
    secrets_meta_raw = check_output(
        f"JUJU_MODEL={model_full_name} juju list-secrets --format json",
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    ).strip()
    secrets_meta = json.loads(secrets_meta_raw)

    secret_ids = [
        secret_id
        for secret_id in secrets_meta
        if owner and secrets_meta[secret_id]["owner"] == owner
        if secrets_meta[secret_id]["label"] == label
    ]

    if len(secret_ids)>1:
        raise ValueError(
            f"Multiple secrets carry the same (label, owner) combination: ({label}, {owner})"
        )

    if len(secret_ids)==0:
        raise ValueError(
            f"Secrets with (label, owner) combination: ({label}, {owner}) not found"
        )

    secret_id = secret_ids[0]

    secrets_data_raw = check_output(
        f"JUJU_MODEL={model_full_name} juju show-secret --format json --reveal {secret_id}",
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    )

    secret_data = json.loads(secrets_data_raw)
    return secret_data[secret_id]["content"]["Data"]


def get_kafka_zk_relation_data(model_full_name: str, owner: str, unit_name: str) -> dict[str, str]:
    unit_data = show_unit(unit_name, model_full_name)

    relation_name = "zookeeper"

    kafka_zk_relation_data = {}
    for info in unit_data[unit_name]["relation-info"]:
        if info["endpoint"] == relation_name:
            kafka_zk_relation_data["relation-id"] = info["relation-id"]

            # initially collects all non-secret keys
            kafka_zk_relation_data.update(dict(info["application-data"]))

    user_secret = get_secret_by_label(
        model_full_name,
        label=f"{relation_name}.{kafka_zk_relation_data['relation-id']}.user.secret",
        owner=owner,
    )

    tls_secret = get_secret_by_label(
        model_full_name,
        label=f"{relation_name}.{kafka_zk_relation_data['relation-id']}.tls.secret",
        owner=owner,
    )

    # overrides to secret keys if found
    return kafka_zk_relation_data | user_secret | tls_secret


def get_peer_relation_data(model_full_name: str, unit_name: str) -> dict[str, str]:

    owner, *_ = unit_name.split("/")
    unit_data = show_unit(unit_name, model_full_name)

    relation_name = "cluster"

    relation_data = {}
    for info in unit_data[unit_name]["relation-info"]:
        if info["endpoint"] == relation_name:
            relation_data["relation-id"] = info["relation-id"]

            # initially collects all non-secret keys
            relation_data.update(dict(info["application-data"]))

    user_secret = get_secret_by_label(
        model_full_name,
        label=f"{relation_name}.{owner}.app",
        owner=owner,
    )

    tls_secret = get_secret_by_label(
        model_full_name,
        label=f"{relation_name}.{owner}.unit",
        owner=unit_name,
    )

    # overrides to secret keys if found
    return relation_data | user_secret | tls_secret


def get_zookeeper_connection(
    unit_name: str, owner: str, model_full_name: str
) -> Tuple[List[str], str]:

    data = get_kafka_zk_relation_data(model_full_name, owner, unit_name)

    return [data["username"]], data["uris"]


def get_kafka_users(
        unit_name: str, model_full_name: str
):
    data = get_peer_relation_data(model_full_name, unit_name)

    return [
        key
        for key in data
        if re.match(r"(relation\-[\d]+)", key)
    ]


def check_properties(model_full_name: str, unit: str):
    properties = check_output(
        f"JUJU_MODEL={model_full_name} juju exec cat {ZOOKEEPER_CONF_PATH}/zoo.cfg --unit {unit}",
        stderr=PIPE,
        shell=True,
        universal_newlines=True,
    )
    return properties.splitlines()


def srvr(host: str) -> Dict:
    """Retrieves attributes returned from the 'srvr' 4lw command.

    Specifically for this test, we are interested in the "Mode" of the ZK server,
    which allows checking quorum leadership and follower active status.
    """
    response = check_output(
        f"echo srvr | nc {host} 2181", stderr=PIPE, shell=True, universal_newlines=True
    )

    result = {}
    for item in response.splitlines():
        k = re.split(": ", item)[0]
        v = re.split(": ", item)[1]
        result[k] = v

    return result


async def ping_servers(ops_test: OpsTest, zookeeper_app_name: str) -> bool:
    for unit in ops_test.model.applications[zookeeper_app_name].units:
        host = unit.public_address
        mode = srvr(host)["Mode"]
        if mode not in ["leader", "follower"]:
            return False

    return True
