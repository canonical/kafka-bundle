#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Application charm that connects to database charms.

This charm is meant to be used only for testing
of the libraries in this repository.
"""

import logging
import os

from charms.tls_certificates_interface.v1.tls_certificates import (
    TLSCertificatesRequiresV1,
    generate_csr,
    generate_private_key,
)
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
        self.certificates = TLSCertificatesRequiresV1(self, "certificates")

        self.framework.observe(getattr(self.on, "start"), self._on_start)
        self.framework.observe(self.on[PEER].relation_created, self._pass)
        self.framework.observe(self.on[PEER].relation_joined, self._pass)
        self.framework.observe(self.on[REL_NAME].relation_created, self._set_data)
        self.framework.observe(self.on[REL_NAME].relation_changed, self._log)
        self.framework.observe(self.on[REL_NAME].relation_broken, self._log)

        self.framework.observe(getattr(self.on, "make_admin_action"), self._make_admin)
        self.framework.observe(getattr(self.on, "remove_admin_action"), self._remove_admin)
        self.framework.observe(getattr(self.on, "change_topic_action"), self._change_topic)
        self.framework.observe(getattr(self.on, "produce_action"), self._produce)
        self.framework.observe(getattr(self.on, "consume_action"), self._consume)

        self.framework.observe(self.on["certificates"].relation_joined, self._tls_relation_joined)
        self.framework.observe(
            self.certificates.on.certificate_available, self._on_certificate_available
        )

    @property
    def relation(self):
        return self.model.get_relation(PEER)

    def _pass(self, _) -> None:
        pass

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

        private_key = self.relation.data[self.app].get("private-key", None)
        ca = self.relation.data[self.app].get("ca", None)
        cert = self.relation.data[self.app].get("certificate", None)

        producer = KafkaProducer(
            bootstrap_servers=servers,
            sasl_plain_username=username,
            sasl_plain_password=password,
            sasl_mechanism="SCRAM-SHA-512",
            security_protocol="SASL_SSL" if private_key else "SASL_PLAINTEXT",
            ssl_cafile="/tmp/ca.pem" if ca else None,
            ssl_certfile="/tmp/server.pem" if cert else None,
            ssl_keyfile="/tmp/server.key" if private_key else None,
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
            return

        private_key = self.relation.data[self.app].get("private-key", None)
        ca = self.relation.data[self.app].get("ca", None)
        cert = self.relation.data[self.app].get("certificate", None)

        KafkaConsumer(
            self.model.get_relation(REL_NAME).data[self.app]["topic"],
            bootstrap_servers=servers,
            sasl_plain_username=username,
            sasl_plain_password=password,
            sasl_mechanism="SCRAM-SHA-512",
            security_protocol="SASL_SSL" if private_key else "SASL_PLAINTEXT",
            ssl_cafile="/tmp/ca.pem" if ca else None,
            ssl_certfile="/tmp/server.pem" if cert else None,
            ssl_keyfile="/tmp/server.key" if private_key else None,
        )
        event.set_results({"result": "read"})

    @staticmethod
    def write_file(content: str, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

    def _tls_relation_joined(self, _) -> None:
        self.relation.data[self.app].update(
            {"private-key": generate_private_key().decode("utf-8")}
        )
        self._request_certificate()

    def _request_certificate(self):
        private_key = self.relation.data[self.app].get("private-key", None)
        if not private_key:
            return

        csr = generate_csr(
            private_key=private_key.encode("utf-8"),
            subject=os.uname()[1],
        ).strip()

        self.certificates.request_certificate_creation(certificate_signing_request=csr)

    def _on_certificate_available(self, event) -> None:
        if not self.relation:
            event.defer()
            return

        self.write_file(
            content=self.relation.data[self.app].get("private-key"), path="/tmp/server.key"
        )
        self.write_file(content=event.certificate, path="/tmp/server.pem")
        self.write_file(content=event.ca, path="/tmp/ca.pem")


if __name__ == "__main__":
    main(ApplicationCharm)
