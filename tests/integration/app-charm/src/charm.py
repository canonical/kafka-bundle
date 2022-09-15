#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Application charm that connects to database charms.

This charm is meant to be used only for testing
of the libraries in this repository.
"""

import logging

from ops.charm import CharmBase, RelationEvent
from ops.main import main
from ops.model import ActiveStatus
from kafka import KafkaConsumer, KafkaProducer

logger = logging.getLogger(__name__)


CHARM_KEY = "app"
PEER = "cluster"
REL_NAME = "kafka-client"
ZK = "zookeeper"


class ApplicationCharm(CharmBase):
    """Application charm that connects to database charms."""

    def __init__(self, *args):
        super().__init__(*args)
        self.name = CHARM_KEY

        self.framework.observe(getattr(self.on, "start"), self._on_start)
        self.framework.observe(self.on[REL_NAME].relation_created, self._set_data)
        self.framework.observe(self.on[REL_NAME].relation_changed, self._log)
        self.framework.observe(self.on[REL_NAME].relation_broken, self._log)

        self.framework.observe(getattr(self.on, "make_admin_action"), self._make_admin)
        self.framework.observe(getattr(self.on, "remove_admin_action"), self._remove_admin)
        self.framework.observe(getattr(self.on, "change_topic_action"), self._change_topic)
        self.framework.observe(getattr(self.on, "produce_action"), self._produce)
        self.framework.observe(getattr(self.on, "consume_action"), self._consume)

    @property
    def relation(self):
        return self.model.get_relation(REL_NAME)

    def _on_start(self, _) -> None:
        self.unit.status = ActiveStatus()

    def _set_data(self, event: RelationEvent) -> None:

        event.relation.data[self.unit].update({"group": self.unit.name.split("/")[1]})

        if not self.unit.is_leader():
            return
        event.relation.data[self.app].update(
            {"extra-user-roles": "producer,consumer", "topic": "test-topic"}
        )

    def _make_admin(self, _):
        self.model.get_relation(REL_NAME).data[self.app].update(
            {"extra-user-roles": "admin,consumer,producer"}
        )

    def _remove_admin(self, _):
        self.model.get_relation(REL_NAME).data[self.app].update({"extra-user-roles": "producer"})

    def _change_topic(self, _):
        self.model.get_relation(REL_NAME).data[self.app].update({"topic": "test-topic-changed"})

    def _log(self, event: RelationEvent):
        return

    def _produce(self, event):
        try:
            relation_list = self.model.relations[REL_NAME]
            servers = relation_list[0].data[relation_list[0].app]["endpoints"].split(",")
            username = relation_list[0].data[relation_list[0].app]["username"]
            password = relation_list[0].data[relation_list[0].app]["password"]

            producer = KafkaProducer(
                bootstrap_servers=servers,
                sasl_plain_username=username,
                sasl_plain_password=password,
                sasl_mechanism="SCRAM-SHA-512",
                security_protocol="SASL_PLAINTEXT",
            )
            producer.send("test-topic", b"test-message")
            event.set_results({"result": "sent"})
        except TypeError:
            message = "No relations data found.  Terminating produce action."
            event.fail(message=message)
            logger.info(message)

    def _consume(self, event):
        try:
            relation_list = self.model.relations[REL_NAME]
            servers = relation_list[0].data[relation_list[0].app]["endpoints"].split(",")
            username = relation_list[0].data[relation_list[0].app]["username"]
            password = relation_list[0].data[relation_list[0].app]["password"]

            consumer = KafkaConsumer(
                "test-topic",
                bootstrap_servers=servers,
                sasl_plain_username=username,
                sasl_plain_password=password,
                sasl_mechanism="SCRAM-SHA-512",
                security_protocol="SASL_PLAINTEXT",
            )
            for msg in consumer:
                logger.info(msg)
                if msg == "test-message":
                    event.set_results({"result": "pass"})
        except TypeError:
            message = "No relations data found.  Terminating consume action."
            event.fail(message=message)
            logger.info(message)


if __name__ == "__main__":
    main(ApplicationCharm)
