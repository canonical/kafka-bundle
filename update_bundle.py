#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import sys
from pathlib import Path

import requests
import yaml

logger = logging.getLogger(__name__)


def fetch_revision(charm: str, charm_channel: str) -> int:
    """Returns revision number for charm in channel.

    Args:
        charm: the name of the charm in CharmHub
        charm_channel: the desired charm channel in CharmHub

    Returns:
        Integer of revision number for most recent channel revision
    """
    charm_info = requests.get(
        f"https://api.snapcraft.io/v2/charms/info/{charm}?fields=channel-map"
    ).json()
    revisions = []
    for channel in charm_info["channel-map"]:
        if channel["channel"]["risk"] == charm_channel:
            revisions.append(channel["revision"]["revision"])
    
    if not revisions:
        raise ValueError("Revision not found.")

    return max(revisions)

def update_bundle(bundle_path: str) -> None:
    """Updates a bundle's revision number.

    Args:
        bundle_path: path to the bundle.yaml to update
    """
    bundle_data = yaml.safe_load(Path(bundle_path).read_text())
    for app in bundle_data["applications"]:
        bundle_data["applications"][app]["revision"] = fetch_revision(
            app, bundle_data["applications"][app]["channel"]
        )

    with open(bundle_path, "w") as bundle:
        yaml.dump(bundle_data, bundle)
        bundle.close()


if __name__ == "__main__":
    update_bundle(sys.argv[1])
