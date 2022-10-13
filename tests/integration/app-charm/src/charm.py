#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Application charm that connects to database charms.

This charm is meant to be used only for testing
of the libraries in this repository.
"""

import logging
import os
import threading
import time
from typing import List, Optional

from charms.tls_certificates_interface.v1.tls_certificates import (
    CertificateAvailableEvent,
    TLSCertificatesRequiresV1,
    generate_csr,
    generate_private_key,
)
from kafka import KafkaConsumer, KafkaProducer
from ops.charm import ActionEvent, CharmBase, RelationEvent
from ops.framework import EventBase
from ops.main import main
from ops.model import ActiveStatus, Relation

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
        self.framework.observe(getattr(self.on, "produce_consume_action"), self._produce_consume)

        self.framework.observe(self.on["certificates"].relation_joined, self._tls_relation_joined)
        self.framework.observe(
            self.certificates.on.certificate_available, self._on_certificate_available
        )

    @property
    def relation(self):
        return self.model.get_relation(PEER)

    @property
    def client_relation(self):
        return self.model.get_relation(REL_NAME)

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

    def _make_admin(self, event: ActionEvent) -> None:
        if not self.client_relation:
            event.fail("No client relation")
            return

        self.client_relation.data[self.app].update({"extra-user-roles": "admin,consumer,producer"})

    def _remove_admin(self, event: ActionEvent) -> None:
        if not self.client_relation:
            event.fail("No client relation")
            return

        self.client_relation.data[self.app].update({"extra-user-roles": "producer"})

    def _change_topic(self, event: ActionEvent) -> None:
        if not self.client_relation:
            event.fail("No client relation")
            return

        self.client_relation.data[self.app].update({"topic": "test-topic-changed"})

    def _log(self, _) -> None:
        return

    def _produce_consume(self, event: ActionEvent):
        if not self.relation:
            event.fail("No peer relation")
            return

        private_key = self.relation.data[self.app].get("private-key", None)

        relation_list = self.model.relations[REL_NAME]
        relation = relation_list[0] or None
        if not relation:
            message = "No relations data found.  Terminating produce-consume action."
            logger.info(message)
            event.fail(message=message)
            return

        app = relation.app or None
        if not app:
            message = "No relations data found.  Terminating produce-consume action."
            logger.info(message)
            event.fail(message=message)
            return

        servers = relation.data[app].get("uris", "")
        if private_key:
            servers = servers.replace("9092", "9093")
        servers = servers.split(",")

        username = relation.data[app].get("username", "")
        password = relation.data[app].get("password", "")
        group_id = relation.data[app].get("consumer-group-prefix")

        tasks = [
            Producer(
                charm=self,
                servers=servers,
                username=username,
                password=password,
                private_key=private_key,
                relation=self.relation,
            ),
            Consumer(
                charm=self,
                servers=servers,
                username=username,
                password=password,
                private_key=private_key,
                relation=self.relation,
                group_id=f"{group_id}1",
            ),
        ]

        for t in tasks:
            t.start()

        time.sleep(5)

        try:
            for task in tasks:
                task.join()
            event.set_results({"passed": "true"})
        except KeyError as e:
            logger.error(str(e))
            event.fail(message=str(e))
            raise e

    @staticmethod
    def write_file(content: str, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

    def _tls_relation_joined(self, event: EventBase) -> None:
        if not self.relation:
            event.defer()
            return

        self.relation.data[self.app].update(
            {"private-key": generate_private_key().decode("utf-8")}
        )
        self._request_certificate()

    def _request_certificate(self):
        if not self.relation:
            return

        private_key = self.relation.data[self.app].get("private-key", None)
        if not private_key:
            return

        csr = generate_csr(
            private_key=private_key.encode("utf-8"),
            subject=os.uname()[1],
        ).strip()

        self.certificates.request_certificate_creation(certificate_signing_request=csr)

    def _on_certificate_available(self, event: CertificateAvailableEvent) -> None:
        if not self.relation:
            event.defer()
            return

        self.write_file(
            content=self.relation.data[self.app].get("private-key", ""), path="/tmp/server.key"
        )
        self.write_file(content=event.certificate, path="/tmp/server.pem")
        self.write_file(content=event.ca, path="/tmp/ca.pem")


class Producer(threading.Thread):
    def __init__(
        self,
        charm: CharmBase,
        servers: List[str],
        username: str,
        password: str,
        relation: Relation,
        private_key: Optional[str] = None,
    ):
        self.charm = charm
        self.servers = servers
        self.username = username
        self.password = password
        self.private_key = private_key
        self.relation = relation

        threading.Thread.__init__(self)

    def run(self):
        logger.info("starting producer...")
        producer = KafkaProducer(
            bootstrap_servers=self.servers,
            sasl_plain_username=self.username,
            sasl_plain_password=self.password,
            sasl_mechanism="SCRAM-SHA-512",
            security_protocol="SASL_SSL" if self.private_key else "SASL_PLAINTEXT",
            ssl_cafile="/tmp/ca.pem" if self.private_key else None,
            ssl_certfile="/tmp/server.pem" if self.private_key else None,
            ssl_keyfile="/tmp/server.key" if self.private_key else None,
            ssl_check_hostname=False,
        )

        for _ in range(15):
            producer.send("test-topic", b"test-message")
            time.sleep(1)

        producer.close()


class Consumer(threading.Thread):
    def __init__(
        self,
        charm: CharmBase,
        servers: List[str],
        username: str,
        password: str,
        relation: Relation,
        group_id: str,
        private_key: Optional[str] = None,
    ):
        self.charm = charm
        self.servers = servers
        self.username = username
        self.password = password
        self.private_key = private_key
        self.relation = relation
        self.group_id = group_id

        threading.Thread.__init__(self)

    def run(self):
        logger.info("starting consumer...")
        consumer = KafkaConsumer(
            "test-topic",
            bootstrap_servers=self.servers,
            sasl_plain_username=self.username,
            sasl_plain_password=self.password,
            sasl_mechanism="SCRAM-SHA-512",
            security_protocol="SASL_SSL" if self.private_key else "SASL_PLAINTEXT",
            ssl_cafile="/tmp/ca.pem" if self.private_key else None,
            ssl_certfile="/tmp/server.pem" if self.private_key else None,
            ssl_keyfile="/tmp/server.key" if self.private_key else None,
            ssl_check_hostname=False,
            group_id=self.group_id,
            enable_auto_commit=True,
            auto_offset_reset="earliest",
            consumer_timeout_ms=15000,
        )

        self.message_found = False
        for message in consumer:
            logger.info(message)
            if message == b"test-message":
                self.message_found = True

        consumer.close()

        if not self.message_found:
            raise KeyError("Could not find produced message in consumer stream")


if __name__ == "__main__":
    main(ApplicationCharm)
