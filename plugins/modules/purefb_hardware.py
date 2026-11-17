#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2021, Simon Dodsley (simon@everpuredata.com)
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {
    "metadata_version": "1.1",
    "status": ["preview"],
    "supported_by": "community",
}

DOCUMENTATION = r"""
---
module: purefb_hardware
version_added: '1.15.0'
short_description: Manage FlashBlade Hardware
description:
- Enable or disable FlashBlade visual identification lights and set connector parameters.
- Connectors are managed through the C(/network-interfaces/connectors) endpoint on
  arrays with REST API version 2.17 or higher and through the deprecated
  C(/hardware-connectors) endpoint on older arrays.
- Changing the speed or breakout of a connector is disruptive, requires a transceiver
  to be inserted and the port must not be a member of a link aggregation group.
  Remove the port from its LAG with M(everpure.flashblade.purefb_lag) first.
- The legacy pair I(speed) and I(ports) and the pair I(port_speed) and I(lanes_per_port)
  describe the same configuration in two forms and cannot be combined. Only the
  I(port_speed) form can configure 200Gb and 400Gb ports.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of hardware component
    type: str
    required: true
  enabled:
    description:
    - State of the component identification LED
    - Components without an identification LED, such as connectors and power
      supplies, report no LED state. C(false) is ignored with a warning and
      C(true) fails.
    type: bool
  speed:
    description:
    - If the component specified is a connector, set the configured speed
      of each lane in the connector in gigabits-per-second
    - Legacy form, mutually exclusive with I(port_speed) and I(lanes_per_port)
    type: int
    choices: [ 10, 25, 40 ]
  ports:
    description:
    - If the component specified is a connector, the number of configured
      ports in the connector
    - Legacy form, mutually exclusive with I(port_speed) and I(lanes_per_port)
    type: int
    choices: [ 1, 4 ]
  port_speed:
    description:
    - If the component specified is a connector, the configured speed of each
      port in the connector in gigabits-per-second
    - Must be set together with I(lanes_per_port)
    - Requires Purity//FB with REST API version 2.20 or higher
    type: int
    choices: [ 10, 25, 40, 50, 100, 200, 400 ]
    version_added: '1.30.0'
  lanes_per_port:
    description:
    - If the component specified is a connector, the number of lanes that make up
      each port in the connector
    - Must be set together with I(port_speed)
    - Requires Purity//FB with REST API version 2.20 or higher
    type: int
    choices: [ 1, 2, 4, 8 ]
    version_added: '1.30.0'
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Set connector to be 4 x 40Gb ports
  everpure.flashblade.purefb_hardware:
    name: "CH1.FM1.ETH1"
    speed: 40
    ports: 4
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Set connector to be 4 x 25Gb breakout ports
  everpure.flashblade.purefb_hardware:
    name: "CH1.FM1.ETH1"
    port_speed: 25
    lanes_per_port: 1
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Set connector to be 1 x 100Gb port
  everpure.flashblade.purefb_hardware:
    name: "CH1.FM1.ETH1"
    port_speed: 100
    lanes_per_port: 4
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Set connector to be 1 x 400Gb port
  everpure.flashblade.purefb_hardware:
    name: "CH1.FM1.ETH1"
    port_speed: 400
    lanes_per_port: 8
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Enable identification LED
  everpure.flashblade.purefb_hardware:
    name: "CH1.FB1"
    enabled: true
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Disable identification LED
  everpure.flashblade.purefb_hardware:
    name: "CH1.FB1"
    enabled: false
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient import flashblade
except ImportError:
    HAS_PYPURECLIENT = False

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
    get_rest_api_version,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

# /network-interfaces/connectors replaces the deprecated /hardware-connectors
CONNECTOR_API_VERSION = "2.17"
# port_speed + lanes_per_port form of the connector configuration
PORT_SPEED_API_VERSION = "2.20"
GBPS = 1000000000
CONNECTOR_PARAMS = ("speed", "ports", "port_speed", "lanes_per_port")


def _use_network_connectors(api_version):
    """True when the array serves /network-interfaces/connectors."""
    return LooseVersion(CONNECTOR_API_VERSION) <= LooseVersion(api_version)


def get_hardware(module, blade, name):
    """Return the hardware component called name, failing when it does not exist."""
    res = blade.get_hardware(names=[name])
    if res.status_code != 200:
        module.fail_json(
            msg="Hardware component {0} does not exist. Error: {1}".format(
                name, get_error_message(res)
            )
        )
    items = list(res.items)
    if not items:
        module.fail_json(msg="Hardware component {0} does not exist".format(name))
    return items[0]


def get_connector(module, blade, api_version, name):
    """Return the connector called name, failing when it is not a connector."""
    if _use_network_connectors(api_version):
        res = blade.get_network_interfaces_connectors(names=[name])
    else:
        res = blade.get_hardware_connectors(names=[name])
    if res.status_code != 200:
        module.fail_json(
            msg=(
                "Hardware component {0} is not a connector or does not exist. "
                "Error: {1}"
            ).format(name, get_error_message(res))
        )
    items = list(res.items)
    if not items:
        module.fail_json(msg="Hardware component {0} is not a connector".format(name))
    return items[0]


def patch_connector(blade, api_version, name, body):
    """PATCH a connector through the endpoint the array supports."""
    if _use_network_connectors(api_version):
        return blade.patch_network_interfaces_connectors(
            names=[name], network_connector=body
        )
    return blade.patch_hardware_connectors(names=[name], hardware_connector=body)


def connector_changes(module, connector):
    """Return the connector fields to send, or an empty dict when nothing differs.

    The array interprets lane_speed/port_count and port_speed/lanes_per_port
    as pairs, so the whole requested pair is sent in one PATCH when any of its
    fields differs from the current configuration. The two forms are never mixed.
    """
    desired = {}
    if module.params["port_speed"] is not None:
        desired["port_speed"] = module.params["port_speed"] * GBPS
        desired["lanes_per_port"] = module.params["lanes_per_port"]
    else:
        if module.params["speed"] is not None:
            desired["lane_speed"] = module.params["speed"] * GBPS
        if module.params["ports"] is not None:
            desired["port_count"] = module.params["ports"]
    for field, value in desired.items():
        if getattr(connector, field, None) != value:
            return desired
    return {}


def update_led(module, blade, hardware):
    """Set the identification LED. Return True when a change is or would be made.

    Components without an identification LED (connectors and power supplies)
    report identify_enabled as None. Disabling such an LED is a no-op and
    enabling it fails, so a run never reports a change the array cannot make.
    """
    name = module.params["name"]
    enabled = module.params["enabled"]
    if hardware.identify_enabled is None:
        if enabled:
            module.fail_json(
                msg="Hardware component {0} has no identification LED".format(name)
            )
        module.warn(
            "Hardware component {0} has no identification LED, enabled ignored".format(
                name
            )
        )
        return False
    if hardware.identify_enabled == enabled:
        return False
    if not module.check_mode:
        res = blade.patch_hardware(
            names=[name],
            hardware=flashblade.Hardware(identify_enabled=enabled),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to set identification LED for {0}. Error: {1}".format(
                    name, get_error_message(res)
                )
            )
    return True


def update_connector(module, blade, api_version, connector):
    """Apply the requested connector configuration. Return True on change."""
    name = module.params["name"]
    changes = connector_changes(module, connector)
    if not changes:
        return False
    if not module.check_mode:
        res = patch_connector(
            blade, api_version, name, flashblade.HardwareConnector(**changes)
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to change connector configuration for {0}. Error: {1}".format(
                    name, get_error_message(res)
                )
            )
    return True


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            enabled=dict(type="bool"),
            name=dict(type="str", required=True),
            speed=dict(
                type="int",
                choices=[10, 25, 40],
            ),
            ports=dict(
                type="int",
                choices=[1, 4],
            ),
            port_speed=dict(
                type="int",
                choices=[10, 25, 40, 50, 100, 200, 400],
            ),
            lanes_per_port=dict(
                type="int",
                choices=[1, 2, 4, 8],
            ),
        )
    )

    module = AnsibleModule(
        argument_spec,
        mutually_exclusive=[
            ["speed", "port_speed"],
            ["speed", "lanes_per_port"],
            ["ports", "port_speed"],
            ["ports", "lanes_per_port"],
        ],
        required_together=[["port_speed", "lanes_per_port"]],
        supports_check_mode=True,
    )
    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)

    if module.params["port_speed"] is not None and LooseVersion(
        PORT_SPEED_API_VERSION
    ) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "port_speed and lanes_per_port require Purity//FB "
                "REST API version {0} or higher"
            ).format(PORT_SPEED_API_VERSION)
        )

    # Resolve every object first so a name that fails validation never
    # leaves a partial change (for example an LED toggled before a connector
    # error) behind a failed task.
    name = module.params["name"]
    hardware = None
    connector = None
    if module.params["enabled"] is not None:
        hardware = get_hardware(module, blade, name)
    if any(module.params[param] is not None for param in CONNECTOR_PARAMS):
        connector = get_connector(module, blade, api_version, name)

    changed = False
    if hardware is not None:
        changed = update_led(module, blade, hardware)
    if connector is not None:
        changed = update_connector(module, blade, api_version, connector) or changed

    module.exit_json(changed=changed)


if __name__ == "__main__":
    main()
