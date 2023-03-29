#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import random
import string
from typing import Dict

from juju.unit import Unit
from pymongo import MongoClient

logger = logging.getLogger()


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

        assert len(consumed_messages) >= len(produced_messages)
        assert abs(len(consumed_messages) - len(produced_messages)) < 3

        client.close()
    except Exception as e:
        logger.error("Cannot connect to MongoDB collection.")
        raise e


async def fetch_action_get_credentials(unit: Unit) -> Dict:
    """Helper to run an action to fetch connection info.

    Args:
        unit: The juju unit on which to run the get_credentials action for credentials
    Returns:
        A dictionary with the username, password and access info for the service.
    """
    action = await unit.run_action(action_name="get-credentials")
    result = await action.wait()
    return result.results


def get_action_parameters(credentials: Dict[str, str], topic_name: str):
    """Construct parameter dictionary needed to stark consumer/producer with the action."""
    logger.info(f"Credentials: {credentials}")
    assert "kafka" in credentials
    action_data = {
        "servers": credentials["kafka"]["endpoints"],
        "username": credentials["kafka"]["username"],
        "password": credentials["kafka"]["password"],
        "topic_name": topic_name,
    }
    if "consumer-group-prefix" in credentials["kafka"]:
        action_data["consumer_group_prefix"] = credentials["kafka"]["consumer-group-prefix"]
    return action_data


async def fetch_action_start_process(unit: Unit, action_params: Dict[str, str]) -> Dict:
    """Helper to run an action to fetch connection info.

    Args:
        unit: the target unit.
        action_params: A dictionary that contains all commands parameters.

    Returns:
        A dictionary with the result of the action.
    """
    action = await unit.run_action(action_name="start-process", **action_params)
    result = await action.wait()
    return result.results


def get_random_topic() -> str:
    """Return a random topic name."""
    return f"topic-{''.join(random.choices(string.ascii_lowercase, k=4))}"
