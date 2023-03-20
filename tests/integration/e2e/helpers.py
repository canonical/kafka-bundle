import logging
from typing import Dict
from juju.unit import Unit

logger = logging.getLogger()
from pymongo import MongoClient

def check_messages(uris: str, collection_name: str):
    logger.info(f"MongoDB uris: {uris}")
    logger.info(f"Topic: {collection_name}")
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
            elem = (document["origin"], document["content"])
            consumed_messages.append(elem)
        
        cursor = producer_collection.find({})
        for document in cursor:
            elem = (document["origin"], document["content"])
            produced_messages.append(elem)

        logger.info(f"Number of produced messages: {len(produced_messages)}")
        logger.info(f"Number of unique produced messages: {len(set(produced_messages))}")
        logger.info(f"Number of consumed messages: {len(consumed_messages)}")
        logger.info(f"Number of unique consumed messages: {len(set(consumed_messages))}")

        assert consumer_collection.count_documents({}) == producer_collection.count_documents({})

        client.close()
    except Exception as e:
        logger.error("Cannot connect to MongoDB collection.")
        raise e
    
async def fetch_action_get_credentials(unit: Unit) -> Dict:
    """Helper to run an action to fetch connection info.
    Args:
        unit: The juju unit on which to run the get_credentials action for credentials
    Returns:
        A dictionary with the username, password and access info for the service
    """
    action = await unit.run_action(action_name="get-credentials")
    result = await action.wait()
    return result.results