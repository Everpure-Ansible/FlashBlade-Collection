#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2020, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_inventory
version_added: '1.0.0'
short_description: Collect information from Everpure FlashBlade
description:
  - Collect the hardware inventory of an Everpure FlashBlade running the
    Purity//FB operating system. The module reports the chassis, fabric
    modules, blades, bays, fans, power supplies, Ethernet and management
    ports and the configuration of the network connectors, including
    identification LED state, part and serial numbers, MAC addresses and
    temperature sensor readings where the Purity//FB version provides them.
author:
  - Everpure ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
extends_documentation_fragment:
  - everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: collect FlashBlade inventory
  everpure.flashblade.purefb_inventory:
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
  register: blade_info
- name: show default information
  debug:
    msg: "{{ blade_info['purefb_info'] }}"
"""

RETURN = r"""
purefb_info:
  description: Returns the hardware inventory of the FlashBlade
  returned: always
  type: dict
  contains:
    modules:
      description: Fabric modules keyed by component name
      type: dict
    ethernet:
      description: Ethernet ports keyed by component name
      type: dict
    mgmt_ports:
      description: Management ports keyed by component name
      type: dict
    fans:
      description: Fans keyed by component name
      type: dict
    bays:
      description: Blade bays keyed by component name
      type: dict
    controllers:
      description: Controllers keyed by component name
      type: dict
    blades:
      description: Blades keyed by component name
      type: dict
    chassis:
      description: Chassis keyed by component name
      type: dict
    power:
      description: Power supplies keyed by component name
      type: dict
    switch:
      description: External fabric modules keyed by component name
      type: dict
    connectors:
      description:
        - Network connector configuration keyed by connector name, including
          connector type, lane speed, port count, port speed, lanes per port
          and transceiver type
      type: dict
"""


from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
    get_rest_api_version,
)

PART_NUMBER_API_VERSION = "2.8"
MAC_API_VERSION = "2.16"
CONNECTOR_API_VERSION = "2.17"
SENSOR_API_VERSION = "2.18"
LANES_PER_PORT_API_VERSION = "2.20"


def _read_items(module, res, what):
    """Return the items of a read, or fail with the answer of the array."""
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read {0}. Error: {1}".format(what, get_error_message(res))
        )
    return list(res.items)


def _get_components(module, blade, hw_type):
    """Return the hardware components of one type."""
    return _read_items(
        module,
        blade.get_hardware(filter="type='{0}'".format(hw_type)),
        "the hardware inventory",
    )


def _sensor_readings(component):
    """Return the temperature sensor readings of a component as plain dicts."""
    readings = []
    for sensor in getattr(component, "sensor_readings", None) or []:
        thresholds = getattr(sensor, "thresholds", None)
        readings.append(
            {
                "name": getattr(sensor, "name", None),
                "reading": getattr(sensor, "reading", None),
                "status": getattr(sensor, "status", None),
                "thresholds": {
                    "critical": getattr(thresholds, "critical", None),
                    "non_critical": getattr(thresholds, "non_critical", None),
                    "unrecoverable": getattr(thresholds, "unrecoverable", None),
                },
            }
        )
    return readings


def _common_fields(component, api_version):
    """Fields reported for every component type, gated by REST version."""
    fields = {"details": getattr(component, "details", None)}
    if LooseVersion(PART_NUMBER_API_VERSION) <= LooseVersion(api_version):
        fields["part_number"] = component.part_number
    if LooseVersion(MAC_API_VERSION) <= LooseVersion(api_version):
        fields["data_mac"] = getattr(component, "data_mac", None)
        fields["management_mac"] = getattr(component, "management_mac", None)
    if LooseVersion(SENSOR_API_VERSION) <= LooseVersion(api_version):
        fields["sensor_readings"] = _sensor_readings(component)
    return fields


def generate_connectors_dict(module, blade, api_version):
    """Return the network connector configuration keyed by connector name."""
    if LooseVersion(CONNECTOR_API_VERSION) <= LooseVersion(api_version):
        res = blade.get_network_interfaces_connectors()
    else:
        res = blade.get_hardware_connectors()
    connectors = {}
    for connector in _read_items(module, res, "the network connectors"):
        connectors[connector.name] = {
            "connector_type": connector.connector_type,
            "lane_speed": connector.lane_speed,
            "port_count": connector.port_count,
            "port_speed": getattr(connector, "port_speed", None),
            "transceiver_type": getattr(connector, "transceiver_type", None),
        }
        if LooseVersion(LANES_PER_PORT_API_VERSION) <= LooseVersion(api_version):
            connectors[connector.name]["lanes_per_port"] = connector.lanes_per_port
    return connectors


def generate_hardware_dict(module, blade):
    api_version = get_rest_api_version(blade)
    hw_info = {
        "modules": {},
        "ethernet": {},
        "mgmt_ports": {},
        "fans": {},
        "bays": {},
        "controllers": {},
        "blades": {},
        "chassis": {},
        "power": {},
        "switch": {},
        "connectors": {},
    }
    components = _get_components(module, blade, "fm")
    for component in components:
        component_name = component.name
        hw_info["modules"][component_name] = {
            "slot": component.slot,
            "status": component.status,
            "serial": component.serial,
            "model": component.model,
            "identify": component.identify_enabled,
        }
        hw_info["modules"][component_name].update(
            _common_fields(component, api_version)
        )
    components = _get_components(module, blade, "eth")
    for component in components:
        component_name = component.name
        hw_info["ethernet"][component_name] = {
            "slot": component.slot,
            "status": component.status,
            "serial": component.serial,
            "model": component.model,
            "speed": component.speed,
        }
        hw_info["ethernet"][component_name].update(
            _common_fields(component, api_version)
        )
    components = _get_components(module, blade, "mgmt_port")
    for component in components:
        component_name = component.name
        hw_info["mgmt_ports"][component_name] = {
            "slot": component.slot,
            "status": component.status,
            "serial": component.serial,
            "model": component.model,
            "speed": component.speed,
        }
        hw_info["mgmt_ports"][component_name].update(
            _common_fields(component, api_version)
        )
    components = _get_components(module, blade, "fan")
    for component in components:
        component_name = component.name
        hw_info["fans"][component_name] = {
            "slot": component.slot,
            "status": component.status,
            "identify": component.identify_enabled,
        }
        hw_info["fans"][component_name].update(_common_fields(component, api_version))
    components = _get_components(module, blade, "fb")
    for component in components:
        component_name = component.name
        hw_info["blades"][component_name] = {
            "slot": component.slot,
            "status": component.status,
            "serial": component.serial,
            "model": component.model,
            "temperature": component.temperature,
            "identify": component.identify_enabled,
        }
        hw_info["blades"][component_name].update(_common_fields(component, api_version))
    components = _get_components(module, blade, "pwr")
    for component in components:
        component_name = component.name
        hw_info["power"][component_name] = {
            "slot": component.slot,
            "status": component.status,
            "serial": component.serial,
            "model": component.model,
        }
        hw_info["power"][component_name].update(_common_fields(component, api_version))
    components = _get_components(module, blade, "xfm")
    for component in components:
        component_name = component.name
        hw_info["switch"][component_name] = {
            "slot": component.slot,
            "status": component.status,
            "serial": component.serial,
            "model": component.model,
        }
        hw_info["switch"][component_name].update(_common_fields(component, api_version))
    components = _get_components(module, blade, "ch")
    for component in components:
        component_name = component.name
        hw_info["chassis"][component_name] = {
            "slot": component.slot,
            "index": component.index,
            "status": component.status,
            "serial": component.serial,
            "model": component.model,
        }
        hw_info["chassis"][component_name].update(
            _common_fields(component, api_version)
        )
    components = _get_components(module, blade, "bay")
    for component in components:
        component_name = component.name
        hw_info["bays"][component_name] = {
            "slot": component.slot,
            "index": component.index,
            "status": component.status,
            "serial": component.serial,
            "model": component.model,
            "identify": component.identify_enabled,
        }
        hw_info["bays"][component_name].update(_common_fields(component, api_version))
    hw_info["connectors"] = generate_connectors_dict(module, blade, api_version)

    return hw_info


def main():
    argument_spec = purefb_argument_spec()

    module = AnsibleModule(argument_spec, supports_check_mode=True)
    blade = get_system(module)
    module.exit_json(changed=False, purefb_info=generate_hardware_dict(module, blade))


if __name__ == "__main__":
    main()
