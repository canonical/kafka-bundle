terraform {
  required_version = ">=1.7.3"

  required_providers {
    juju = {
      version = "=0.23.1"
      source  = "juju/juju"
    }
  }
}
