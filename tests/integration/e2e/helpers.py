#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import random
import string
from subprocess import PIPE, STDOUT, CalledProcessError, check_output
from typing import NamedTuple

import jubilant
from pymongo import MongoClient
from tests.integration.e2e.literals import KAFKA_INTERNAL_PORT, SUBSTRATE

logger = logging.getLogger()

ExecArgs = NamedTuple("ExecArgs", container_arg=str, sudo_arg=str, bin_cmd=str, config_file=str)


def check_produced_and_consumed_messages(uris: str, collection_name: str):
    """Check that messages produced and consumed are consistent."""
    logger.debug(f"MongoDB uris: {uris}")
    logger.debug(f"Topic: {collection_name}")
    produced_messages = []
    consumed_messages = []
    try:
        client = MongoClient(
            uris,
            directConnection=False,
            connect=False,
            serverSelectionTimeoutMS=1000,
            connectTimeoutMS=2000,
        )
        db = client[collection_name]
        consumer_collection = db["consumer"]
        producer_collection = db["producer"]

        logger.info(f"Number of messages from consumer: {consumer_collection.count_documents({})}")
        logger.info(f"Number of messages from producer: {producer_collection.count_documents({})}")
        assert consumer_collection.count_documents({}) > 0
        assert producer_collection.count_documents({}) > 0
        cursor = consumer_collection.find({})
        for document in cursor:
            consumed_messages.append((document["origin"], document["content"]))

        cursor = producer_collection.find({})
        for document in cursor:
            produced_messages.append((document["origin"], document["content"]))

        logger.info(f"Number of produced messages: {len(produced_messages)}")
        logger.info(f"Number of unique produced messages: {len(set(produced_messages))}")
        logger.info(f"Number of consumed messages: {len(consumed_messages)}")
        logger.info(f"Number of unique consumed messages: {len(set(consumed_messages))}")
        if len(consumed_messages) < len(produced_messages):
            missing_elem = list(set(produced_messages) - set(consumed_messages))
            logger.error(missing_elem)

        assert len(consumed_messages) >= len(produced_messages)
        assert abs(len(consumed_messages) - len(produced_messages)) <= 3

        client.close()
    except Exception as e:
        logger.error("Cannot connect to MongoDB collection.")
        raise e


def fetch_action_get_credentials(juju: jubilant.Juju, app: str) -> dict:
    """Helper to run an action to fetch connection info."""
    unit = next(iter(juju.status().apps[app].units.keys()))
    action = juju.run(unit, "get-credentials")
    return action.results


def get_action_parameters(credentials: dict, topic_name: str):
    """Construct parameter dictionary needed to stark consumer/producer with the action."""
    logger.info(f"Credentials: {credentials}")
    assert "kafka" in credentials
    action_data = {
        "servers": credentials["kafka"]["endpoints"],
        "username": credentials["kafka"]["username"],
        "password": credentials["kafka"]["password"],
        "topic-name": topic_name,
    }
    if "consumer-group-prefix" in credentials["kafka"]:
        action_data["consumer-group-prefix"] = credentials["kafka"]["consumer-group-prefix"]
    return action_data


def fetch_action_start_process(
    juju: jubilant.Juju, app: str, action_params: dict[str, str], unit_num: int = 0
) -> dict:
    """Helper to run an action to start consumer/producer.

    Args:
        juju: the Jubilant juju instance.
        app: application name.
        action_params: A dictionary that contains all commands parameters.
        unit_num: number of unit to run action on. Defaults to 0.

    Returns:
        A dictionary with the result of the action.
    """
    unit = list(juju.status().apps[app].units)[unit_num]
    action = juju.run(unit, "start-process", params=action_params)
    return action.results


def fetch_action_stop_process(juju: jubilant.Juju, app: str, unit_num: int = 0) -> dict:
    """Helper to run an action to stop consumer/producer.

    Args:
        juju: the Jubilant juju instance.
        app: application name.
        unit_num: number of unit to run action on. Defaults to 0.

    Returns:
        A dictionary with the result of the action.
    """
    unit = list(juju.status().apps[app].units)[unit_num]
    action = juju.run(unit, "stop-process")
    return action.results


def get_random_topic() -> str:
    """Return a random topic name."""
    return f"topic-{''.join(random.choices(string.ascii_lowercase, k=4))}"


def _get_exec_args_params() -> ExecArgs:
    if SUBSTRATE == "k8s":
        container_arg = "--container kafka"
        sudo_arg = ""
        bin_cmd = "/opt/kafka/bin/kafka-{sub}.sh"
        config_file = "/etc/kafka/client.properties"
    else:
        container_arg = ""
        sudo_arg = "sudo -i"
        bin_cmd = "charmed-kafka.{sub}"
        config_file = "/var/snap/charmed-kafka/current/etc/kafka/client.properties"

    return ExecArgs(container_arg, sudo_arg, bin_cmd, config_file)


def create_topic(model_full_name: str, app_name: str, topic: str) -> None:
    """Helper to create a topic.

    Args:
        model_full_name: Juju model
        app_name: Kafka app name in the Juju model
        topic: the desired topic to configure
    """
    args = _get_exec_args_params()
    try:
        check_output(
            f"JUJU_MODEL={model_full_name} juju ssh {args.container_arg} {app_name}/leader {args.sudo_arg} "
            f"'{args.bin_cmd.format(sub='topics')} --create --topic {topic} --bootstrap-server localhost:{KAFKA_INTERNAL_PORT} "
            f"--command-config {args.config_file}'",
            stderr=STDOUT,
            shell=True,
            universal_newlines=True,
        )

    except CalledProcessError as e:
        logger.error(f"command '{e.cmd}' return with error (code {e.returncode}): {e.output}")
        raise


def write_topic_message_size_config(
    model_full_name: str, app_name: str, topic: str, size: int
) -> None:
    """Helper to configure a topic's message max size.

    Args:
        model_full_name: Juju model
        app_name: Kafka app name in the Juju model
        topic: the desired topic to configure
        size: the maximal message size in bytes
    """
    args = _get_exec_args_params()
    try:
        result = check_output(
            f"JUJU_MODEL={model_full_name} juju ssh {args.container_arg} {app_name}/leader {args.sudo_arg} "
            f"'{args.bin_cmd.format(sub='configs')} --bootstrap-server localhost:{KAFKA_INTERNAL_PORT} "
            f"--entity-type topics --entity-name {topic} --alter --add-config max.message.bytes={size} --command-config {args.config_file}'",
            stderr=STDOUT,
            shell=True,
            universal_newlines=True,
        )

    except CalledProcessError as e:
        logger.error(f"command '{e.cmd}' return with error (code {e.returncode}): {e.output}")
        raise
    assert f"Completed updating config for topic {topic}." in result


def read_topic_config(model_full_name: str, app_name: str, topic: str) -> str:
    """Helper to get a topic's configuration.

    Args:
        model_full_name: Juju model
        app_name: Kafka app name in the Juju model
        topic: the desired topic to read the configuration from
    """
    args = _get_exec_args_params()
    try:
        result = check_output(
            f"JUJU_MODEL={model_full_name} juju ssh {args.container_arg} {app_name}/leader {args.sudo_arg} "
            f"'{args.bin_cmd.format(sub='configs')} --bootstrap-server localhost:{KAFKA_INTERNAL_PORT} "
            f"--entity-type topics --entity-name {topic} --describe --command-config {args.config_file}'",
            stderr=PIPE,
            shell=True,
            universal_newlines=True,
        )

    except CalledProcessError as e:
        logger.error(f"command '{e.cmd}' return with error (code {e.returncode}): {e.output}")
        raise
    return result


def jubilant_all_units_idle(status: jubilant.Status, apps: list[str]):
    """Helper function that checks if all units are in idle state."""
    for app in apps:
        if app not in status.apps:
            return False

        if {
            status.apps[app].units[unit].juju_status.current for unit in status.apps[app].units
        } != {"idle"}:
            return False

    return True
