#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
import re
from subprocess import PIPE, CalledProcessError, check_output
from typing import Any, Dict, List, Set, Tuple

import yaml
from charms.kafka.v0.kafka_snap import SNAP_CONFIG_PATH

from tests.integration.auth import Acl, KafkaAuth

logger = logging.getLogger(__name__)


def load_acls(model_full_name: str, zookeeper_uri: str, unit_name: str) -> Set[Acl]:
    if "k8s" in unit_name:
        command = f"JUJU_MODEL={model_full_name} juju ssh --container kafka {unit_name} 'KAFKA_OPTS=-Djava.security.auth.login.config=/data/kafka/config/kafka-jaas.cfg ./opt/kafka/bin/kafka-acls.sh --authorizer-properties zookeeper.connect={zookeeper_uri} --list --zk-tls-config-file=/data/kafka/config/server.properties'"
    else:
        command = f"JUJU_MODEL={model_full_name} juju ssh {unit_name} 'kafka.acls --authorizer-properties zookeeper.connect={zookeeper_uri} --list --zk-tls-config-file={SNAP_CONFIG_PATH}server.properties'"
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


def check_user(model_full_name: str, username: str, zookeeper_uri: str, unit_name: str) -> None:
    if "k8s" in unit_name:
        command = f"JUJU_MODEL={model_full_name} juju ssh --container kafka {unit_name} 'KAFKA_OPTS=-Djava.security.auth.login.config=/data/kafka/config/kafka-jaas.cfg ./opt/kafka/bin/kafka-configs.sh --zookeeper {zookeeper_uri} --describe --entity-type users --entity-name {username} --zk-tls-config-file=/data/kafka/config/server.properties'"
    else:
        command = f"JUJU_MODEL={model_full_name} juju ssh {unit_name} 'kafka.configs --zookeeper {zookeeper_uri} --describe --entity-type users --entity-name {username} --zk-tls-config-file={SNAP_CONFIG_PATH}server.properties'"
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


def get_zookeeper_connection(unit_name: str, model_full_name: str) -> Tuple[List[str], str]:
    result = show_unit(unit_name=unit_name, model_full_name=model_full_name)

    relations_info = result[unit_name]["relation-info"]

    usernames = []
    zookeeper_uri = ""
    for info in relations_info:
        if info["endpoint"] == "cluster":
            for key in info["application-data"].keys():
                if re.match(r"(relation\-[\d]+)", key):
                    usernames.append(key)
        if info["endpoint"] == "zookeeper":
            zookeeper_uri = info["application-data"]["uris"]

    if zookeeper_uri and usernames:
        return usernames, zookeeper_uri
    else:
        raise Exception("config not found")


def get_kafka_zk_relation_data(unit_name: str, model_full_name: str) -> Dict[str, str]:
    result = show_unit(unit_name=unit_name, model_full_name=model_full_name)
    relations_info = result[unit_name]["relation-info"]

    zk_relation_data = {}
    for info in relations_info:
        if info["endpoint"] == "zookeeper":
            zk_relation_data["chroot"] = info["application-data"]["chroot"]
            zk_relation_data["endpoints"] = info["application-data"]["endpoints"]
            zk_relation_data["password"] = info["application-data"]["password"]
            zk_relation_data["uris"] = info["application-data"]["uris"]
            zk_relation_data["username"] = info["application-data"]["username"]
    return zk_relation_data
