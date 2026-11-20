#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2017, Simon Dodsley (simon@everpuredata.com)
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type


ANSIBLE_METADATA = {
    "metadata_version": "1.1",
    "status": ["preview"],
    "supported_by": "community",
}


DOCUMENTATION = """
---
module: purefb_subnet
version_added: "1.0.0"
short_description:  Manage network subnets in a Everpure FlashBlade
description:
    - This module manages network subnets on Everpure FlashBlade.
    - A subnet is an array-level object. It is shared with a realm using
      M(everpure.flashblade.purefb_resource_access), after which network
      interfaces of the realm can be created in it.
    - Subnets are managed by an array administrator. An administrator whose
      management access is limited to a realm cannot change a subnet that is
      shared with the realm and cannot read the Link Aggregation Groups that
      a new subnet needs. The array refuses these requests and the module
      fails with the error of the array.
author: Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
      - Subnet Name.
      - The name of a subnet takes no realm prefix. A name of the form
        C(realm::name) is refused.
      - An existing subnet is found whatever the letter case of the name.
    required: true
    type: str
  state:
    description:
      - Create, delete or modifies a subnet.
    required: false
    default: present
    choices: [ "present", "absent" ]
    type: str
  lag:
    description:
      - Name of the Link Aggreation Group to use for the subnet.
      - Only used when the subnet is created. The Link Aggregation Group of
        an existing subnet is not changed.
    default: uplink
    type: str
    version_added: "1.7.0"
  gateway:
    description:
      - IPv4 or IPv6 address of subnet gateway.
    required: false
    type: str
  mtu:
    description:
      - MTU size of the subnet. Range is 1280 to 9216.
      - Defaults to 1500 when creating a subnet. When modifying an
        existing subnet an omitted value leaves the current MTU unchanged.
    required: false
    type: int
  prefix:
    description:
      - IPv4 or IPv6 address associated with the subnet.
      - Supply the prefix length (CIDR) as well as the IP address.
      - Required for subnet creation.
    required: false
    type: str
  vlan:
    description:
      - VLAN ID of the subnet.
      - Defaults to 0 when creating a subnet. When modifying an existing
        subnet an omitted value leaves the current VLAN ID unchanged.
    required: false
    type: int
extends_documentation_fragment:
    - everpure.flashblade.everpure.fb
"""

EXAMPLES = """
- name: Create new network subnet named foo
  everpure.flashblade.purefb_subnet:
    name: foo
    prefix: "10.21.200.3/24"
    gateway: 10.21.200.1
    mtu: 9000
    vlan: 2200
    lag: bar
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Change configuration of existing subnet foo
  everpure.flashblade.purefb_subnet:
    name: foo
    state: present
    prefix: "10.21.100.3/24"
    gateway: 10.21.100.1
    mtu: 1500
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Share subnet foo with realm realm_foo
  everpure.flashblade.purefb_resource_access:
    resource_type: subnets
    resource_name: foo
    scope_type: realms
    scope_name: realm_foo
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete network subnet named foo
  everpure.flashblade.purefb_subnet:
    name: foo
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = """
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import Subnet, Reference
except ImportError:
    HAS_PYPURECLIENT = False

try:
    import netaddr

    HAS_NETADDR = True
except ImportError:
    HAS_NETADDR = False

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
)

REALM_NAME_MSG = (
    "Subnet name {0} is not valid: a subnet is an array-level object and its "
    "name takes no realm prefix. Use the purefb_resource_access module to "
    "share a subnet with a realm."
)
ONE_NAME_MSG = (
    "name must be the name of one subnet: in {0} the array reads a comma as "
    "a separator of names."
)


def _refuse_name(module):
    """Refuse a name that cannot be the name of one subnet, before any request

    Subnets are array-level objects. The name rule of the array rejects the
    realm separator on create, with a message that does not mention realms,
    and a lookup of such a name answers like any missing subnet, so check
    mode would predict a create that the array refuses. In a request the
    array reads a comma as a separator of names: such a name reaches several
    subnets while only the first one is compared.
    """
    name = module.params["name"]
    if "::" in name:
        module.fail_json(msg=REALM_NAME_MSG.format(name))
    if "," in name:
        module.fail_json(msg=ONE_NAME_MSG.format(name))


def _missing(error):
    """Tell whether the message of the array says the object does not exist"""
    return "does not exist" in str(error).lower()


def get_subnet(module, blade):
    """Return the subnet of the task, or None when the array has no such subnet

    Only a subnet the array reports as not existing is absent. Any other
    read the array refuses or fails is reported with the error of the array.
    """
    res = blade.get_subnets(names=[module.params["name"]])
    if res.status_code != 200:
        error = get_error_message(res)
        if _missing(error):
            return None
        module.fail_json(
            msg="Failed to read subnet {0}. Error: {1}".format(
                module.params["name"], error
            )
        )
    items = list(res.items)
    return items[0] if items else None


def _get_subnets(module, blade):
    """Return the subnets the array shows, or fail with the error of the array"""
    res = blade.get_subnets()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read the subnets. Error: {0}".format(get_error_message(res))
        )
    return list(res.items)


def _check_lag(module, blade):
    """Fail unless the array returns the LAG that a new subnet is to use

    Only a create uses the LAG, so only a create reads it. A LAG the array
    reports as not existing keeps its own message; any other read the array
    refuses or fails is reported with the error of the array.
    """
    lag = module.params["lag"]
    res = blade.get_link_aggregation_groups(names=[lag])
    if res.status_code != 200:
        error = get_error_message(res)
        if _missing(error):
            module.fail_json(msg="LAG {0} does not exist.".format(lag))
        module.fail_json(msg="Failed to read LAG {0}. Error: {1}".format(lag, error))


def create_subnet(module, blade):
    """Create Subnet"""
    changed = True
    if not module.params["prefix"]:
        module.fail_json(msg="prefix is required for subnet creation")
    if not module.check_mode:
        if module.params["gateway"]:
            res = blade.post_subnets(
                names=[module.params["name"]],
                subnet=Subnet(
                    prefix=module.params["prefix"],
                    vlan=module.params["vlan"],
                    mtu=module.params["mtu"],
                    gateway=module.params["gateway"],
                    link_aggregation_group=Reference(name=module.params["lag"]),
                ),
            )
        else:
            res = blade.post_subnets(
                names=[module.params["name"]],
                subnet=Subnet(
                    prefix=module.params["prefix"],
                    vlan=module.params["vlan"],
                    mtu=module.params["mtu"],
                    link_aggregation_group=Reference(name=module.params["lag"]),
                ),
            )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create subnet {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def modify_subnet(module, blade, subnet):
    """Modify Subnet settings

    The requests name the subnet as the array stores it: a read finds a
    subnet whatever the letter case of the name, a change does not.
    """
    changed = False
    if module.params["prefix"]:
        if module.params["prefix"] != subnet.prefix:
            changed = True
            if not module.check_mode:
                res = blade.patch_subnets(
                    names=[subnet.name],
                    subnet=Subnet(prefix=module.params["prefix"]),
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to change subnet {0} prefix to {1}. Error: {2}".format(
                            module.params["name"],
                            module.params["prefix"],
                            get_error_message(res),
                        )
                    )
    if module.params["vlan"] is not None:
        if module.params["vlan"] != subnet.vlan:
            changed = True
            if not module.check_mode:
                res = blade.patch_subnets(
                    names=[subnet.name],
                    subnet=Subnet(vlan=module.params["vlan"]),
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to change subnet {0} VLAN to {1}. Error: {2}".format(
                            module.params["name"],
                            module.params["vlan"],
                            get_error_message(res),
                        )
                    )
    if module.params["gateway"]:
        if module.params["gateway"] != subnet.gateway:
            changed = True
            if not module.check_mode:
                res = blade.patch_subnets(
                    names=[subnet.name],
                    subnet=Subnet(gateway=module.params["gateway"]),
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to change subnet {0} gateway to {1}. Error: {2}".format(
                            module.params["name"],
                            module.params["gateway"],
                            get_error_message(res),
                        )
                    )
    if module.params["mtu"] is not None:
        if module.params["mtu"] != subnet.mtu:
            changed = True
            if not module.check_mode:
                res = blade.patch_subnets(
                    names=[subnet.name],
                    subnet=Subnet(mtu=module.params["mtu"]),
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to change subnet {0} MTU to {1}. Error: {2}".format(
                            module.params["name"],
                            module.params["mtu"],
                            get_error_message(res),
                        )
                    )
    module.exit_json(changed=changed)


def delete_subnet(module, blade, subnet):
    """Delete Subnet, named as the array stores it"""
    changed = True
    if not module.check_mode:
        res = blade.delete_subnets(names=[subnet.name])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete subnet {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(required=True),
            state=dict(default="present", choices=["present", "absent"]),
            gateway=dict(),
            lag=dict(type="str", default="uplink"),
            mtu=dict(type="int"),
            prefix=dict(),
            vlan=dict(type="int"),
        )
    )

    required_if = [["state", "present", ["prefix"]]]
    module = AnsibleModule(
        argument_spec, required_if=required_if, supports_check_mode=True
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    if not HAS_NETADDR:
        module.fail_json(msg="netaddr module is required")

    _refuse_name(module)
    state = module.params["state"]
    blade = get_system(module)
    subnet = get_subnet(module, blade)

    if state == "present":
        if not subnet:
            # Only a create uses the LAG: the LAG of an existing subnet is
            # left alone, so a change or a delete does not read it
            _check_lag(module, blade)
            # Creation defaults; on modification an omitted value is left alone
            if module.params["mtu"] is None:
                module.params["mtu"] = 1500
            if module.params["vlan"] is None:
                module.params["vlan"] = 0
        if module.params["mtu"] is not None and not (
            1280 <= module.params["mtu"] <= 9216
        ):
            module.fail_json(
                msg="MTU {0} is out of range (1280 to 9216)".format(
                    module.params["mtu"]
                )
            )
        if module.params["vlan"] is not None and not (
            0 <= module.params["vlan"] <= 4094
        ):
            module.fail_json(
                msg="VLAN ID {0} is out of range (0 to 4094)".format(
                    module.params["vlan"]
                )
            )
        if module.params["gateway"]:
            if netaddr.IPAddress(module.params["gateway"]) not in netaddr.IPNetwork(
                module.params["prefix"]
            ):
                module.fail_json(msg="Gateway and subnet are not compatible.")
        subnets = _get_subnets(module, blade)
        # The array matches a name whatever its letter case and returns the
        # stored spelling, which tells the subnet of the task from the others
        own_name = subnet.name if subnet else module.params["name"]
        nrange = netaddr.IPSet([module.params["prefix"]])
        for sub in subnets:
            if (
                module.params["vlan"] is not None
                and sub.vlan == module.params["vlan"]
                and sub.name != own_name
                and hasattr(sub.link_aggregation_group, "name")
            ):
                module.fail_json(
                    msg="VLAN ID {0} is already in use.".format(module.params["vlan"])
                )
            if nrange & netaddr.IPSet([sub.prefix]) and sub.name != own_name:
                module.fail_json(msg="Prefix CIDR overlaps with existing subnet.")

    if state == "present" and not subnet:
        create_subnet(module, blade)
    elif state == "present" and subnet:
        modify_subnet(module, blade, subnet)
    elif state == "absent" and subnet:
        delete_subnet(module, blade, subnet)
    elif state == "absent" and not subnet:
        module.exit_json(changed=False)


if __name__ == "__main__":
    main()
