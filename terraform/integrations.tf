/* resource "juju_integration" "kafka_zookeeper" { */
/*   model = juju_model.kafka.name */
/**/
/*   application { */
/*     name = juju_application.kafka.name */
/*     } */
/**/
/*   application { */
/*     name = juju_application.zookeeper.name */
/*     } */
/**/
/* } */
/**/
/* resource "juju_integration" "kafka_integrator" { */
/*   model = juju_model.kafka.name */
/**/
/*   application { */
/*     name = juju_application.kafka.name */
/*     } */
/**/
/*   application { */
/*     name = juju_application.integrator.name */
/*     } */
/**/
/* } */
/**/
/* resource "juju_integration" "kafka_tls" { */
/*   model = juju_model.kafka.name */
/*   count = true ? 1 : 0  */
/**/
/*   application { */
/*     name = juju_application.kafka.name */
/*     endpoint = "certificates" */
/*     } */
/**/
/*   application { */
/*     name = juju_application.tls[count.index].name */
/*     } */
/**/
/* } */
/**/
/**/
/* resource "juju_integration" "zookeeper_tls" { */
/*   model = juju_model.kafka.name */
/*   count = true ? 1 : 0  */
/**/
/*   application { */
/*     name = juju_application.zookeeper.name */
/*     } */
/**/
/*   application { */
/*     name = juju_application.tls[count.index].name */
/*     } */
/**/
/* } */
/**/
