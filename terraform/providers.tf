terraform {
  required_version = ">= 1.4.2"

  required_providers {
    juju = {
      version = "~> 0.6.0"
      source  = "juju/juju"
    }
  }
}

provider "juju" {}
