#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Application charm that connects to database charms.

This charm is meant to be used only for testing
of the libraries in this repository.
"""

import logging

from kafka import KafkaConsumer, KafkaProducer
from ops.charm import CharmBase, RelationEvent
from ops.main import main
from ops.model import ActiveStatus

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
        except TypeError:
            message = "No relations data found.  Terminating produce action."
            logger.info(message)
            event.fail(message=message)
            return

        producer = KafkaProducer(
            bootstrap_servers=servers,
            sasl_plain_username=username,
            sasl_plain_password=password,
            sasl_mechanism="SCRAM-SHA-512",
            security_protocol="SASL_PLAINTEXT",
        )
        producer.send(self.model.get_relation(REL_NAME).data[self.app]["topic"], b"test-message")
        event.set_results({"result": "sent"})

    def _consume(self, event):
        try:
            relation_list = self.model.relations[REL_NAME]
            servers = relation_list[0].data[relation_list[0].app]["endpoints"].split(",")
            username = relation_list[0].data[relation_list[0].app]["username"]
            password = relation_list[0].data[relation_list[0].app]["password"]
        except TypeError:
            message = "No relations data found.  Terminating consume action."
            logger.info(message)
            event.fail(message=message)

        KafkaConsumer(
            self.model.get_relation(REL_NAME).data[self.app]["topic"],
            bootstrap_servers=servers,
            sasl_plain_username=username,
            sasl_plain_password=password,
            sasl_mechanism="SCRAM-SHA-512",
            security_protocol="SASL_PLAINTEXT",
        )
        event.set_results({"result": "read"})


if __name__ == "__main__":
    main(ApplicationCharm)
