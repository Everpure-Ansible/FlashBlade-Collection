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
module: purefb_network
version_added: "1.0.0"
short_description:  Manage network interfaces in a Everpure FlashBlade
description:
    - This module manages network interfaces on Everpure FlashBlade.
    - When creating a network interface a subnet must already exist with
      a network prefix that covers the IP address of the interface being
      created.
    - To bring up an isolated realm, create an C(egress-only) interface
      first, point the realm's DNS at it with M(everpure.flashblade.purefb_dns),
      create the realm server with M(everpure.flashblade.purefb_server),
      then switch the interface to the C(data) service and attach the server.
      Tear down in the reverse order.
author: Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
      - Interface Name.
    required: true
    type: str
  state:
    description:
      - Create, delete or modifies a network interface.
    required: false
    default: present
    choices: [ "present", "absent" ]
    type: str
  address:
    description:
      - IP address of interface.
    required: false
    type: str
  services:
    description:
      - Define which service is configured for the interface.
      - Defaults to C(data) when creating an interface. When modifying an
        existing interface an omitted value leaves the current service
        unchanged.
      - C(egress-only) requires REST 2.19 (Purity//FB 4.6.1) and carries no
        server; C(sts) requires REST 2.17 (Purity//FB 4.5.6) and always
        uses the default C(_array_server).
      - Moving an interface off the C(data) service disables RDMA on it, and
        moving it to C(egress-only) also detaches any server, as the array
        requires.
    required: false
    choices: [ "data", "replication", "egress-only", "sts" ]
    type: str
  itype:
    description:
      - Type of interface.
    required: false
    choices: [ "vip" ]
    default: vip
    type: str
  attached_server:
    description:
        - Name of the server you want to attach to the interface
        - To attach to a server on a Realm, set the value to realm-1::server-1
        - Only 1 server per Network Interface.
        - Set to an empty string to detach the interface from its server.
          The array keeps the default C(_array_server) on C(data) and C(sts)
          interfaces, so an empty string on those is the same as
          C(_array_server).
        - Requires REST 2.16.
    required: false
    type: str
  rdma_enabled:
    description:
      - Enable RDMA on the interface. Only valid with the C(data) service.
      - When omitted, the array enables RDMA on a new C(data) interface and
        leaves an existing interface unchanged.
      - Requires REST 2.28 (Purity//FB 4.8.4).
    required: false
    type: bool
    version_added: "1.30.0"

extends_documentation_fragment:
    - everpure.flashblade.everpure.fb
"""

EXAMPLES = """
- name: Create new network interface named foo
  everpure.flashblade.purefb_network:
    name: foo
    address: 10.21.200.23
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a data interface with RDMA disabled
  everpure.flashblade.purefb_network:
    name: foo
    address: 10.21.200.23
    services: data
    rdma_enabled: false
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create an egress-only interface for a new realm
  everpure.flashblade.purefb_network:
    name: realm-1-egress
    address: 10.21.200.24
    services: egress-only
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Switch the realm interface to the data service and attach its server
  everpure.flashblade.purefb_network:
    name: realm-1-egress
    address: 10.21.200.24
    services: data
    attached_server: realm-1::server-1
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a new network interface named foo with attached server named server-1 in a Realm named realm-1
  everpure.flashblade.purefb_network:
    name: foo
    address: 10.21.200.23
    attached_server: realm-1::server-1
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Detach network interface foo from its server
  everpure.flashblade.purefb_network:
    name: foo
    address: 10.21.200.23
    attached_server: ""
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create an STS interface for object identity federation
  everpure.flashblade.purefb_network:
    name: sts
    address: 10.21.200.25
    services: sts
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Change IP address of network interface named foo
  everpure.flashblade.purefb_network:
    name: foo
    state: present
    address: 10.21.200.123
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete network interface named foo
  everpure.flashblade.purefb_network:
    name: foo
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = """
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import NetworkInterface, NetworkInterfacePatch
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

SERVERS_API_VERSION = "2.16"
STS_API_VERSION = "2.17"
EGRESS_ONLY_API_VERSION = "2.19"
RDMA_API_VERSION = "2.28"

DEFAULT_SERVER = "_array_server"


def get_iface(module, blade):
    """Return Filesystem or None"""
    res = blade.get_network_interfaces(names=[module.params["name"]])
    if res.status_code == 200:
        return list(res.items)[0]
    return None


def _attached_server_name(iface):
    """Name of the server an interface is attached to, or None.

    ``attached_servers`` is a list of references on the API, even though an
    interface can only carry one server.
    """
    attached = getattr(iface, "attached_servers", None) or []
    if not attached:
        return None
    return getattr(attached[0], "name", None)


def _server_in_sync(wanted, current, services):
    """Whether the attached server already matches what was asked for.

    ``wanted`` is the module option (``""`` means detach) and ``current`` the
    name on the array or None. ``services`` is the service list the interface
    will have after this run. The array never leaves a data or sts interface
    without a server: an empty list sent to either comes back as
    ``_array_server``, and moving an interface to egress-only detaches it on
    the array side. Treating those as in sync keeps a rerun from reporting
    a change it cannot make.
    """
    current = current or ""
    if wanted == current:
        return True
    if wanted == "":
        if "egress-only" in services:
            return True
        if current == DEFAULT_SERVER and ("data" in services or "sts" in services):
            return True
    return False


def create_iface(module, blade):
    """Create Network Interface"""
    changed = True
    if not module.check_mode:
        kwargs = dict(
            address=module.params["address"],
            services=[module.params["services"] or "data"],
            type=module.params["itype"],
        )
        # An empty attached_server is the array default (data falls back to
        # _array_server, everything else has none), so only a name is sent.
        if module.params["attached_server"]:
            kwargs["attached_servers"] = [{"name": module.params["attached_server"]}]
        if module.params["rdma_enabled"] is not None:
            kwargs["rdma_enabled"] = module.params["rdma_enabled"]
        res = blade.post_network_interfaces(
            names=[module.params["name"]],
            network_interface=NetworkInterface(**kwargs),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Interface {0} creation failed. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def modify_iface(module, blade):
    """Modify Network Interface

    Everything that differs is sent in one PATCH.
    """
    changed = False
    iface = get_iface(module, blade)
    patch = {}

    if module.params["address"] != iface.address:
        patch["address"] = module.params["address"]

    # An interface with no services assigned reports them as null
    current_services = getattr(iface, "services", None) or []
    wanted_services = current_services
    if module.params["services"]:
        wanted_services = [module.params["services"]]
        if sorted(wanted_services) != sorted(current_services):
            patch["services"] = wanted_services

    current_rdma = getattr(iface, "rdma_enabled", None)
    if module.params["rdma_enabled"] and "data" not in wanted_services:
        module.fail_json(msg="rdma_enabled is only supported with the data service.")
    if (
        module.params["rdma_enabled"] is not None
        and module.params["rdma_enabled"] != current_rdma
    ):
        patch["rdma_enabled"] = module.params["rdma_enabled"]
    # The array refuses to move an interface off the data service while RDMA
    # is on, so the same PATCH turns it off.
    if (
        "services" in patch
        and "data" in current_services
        and "data" not in wanted_services
        and current_rdma
    ):
        patch["rdma_enabled"] = False

    # Only move the interface when it is not already on the requested server.
    # An interface carries at most one attached server, but the API field is
    # a list, so the current name has to be pulled out of it.
    wanted_server = module.params["attached_server"]
    if wanted_server is not None and not _server_in_sync(
        wanted_server, _attached_server_name(iface), wanted_services
    ):
        if wanted_server:
            patch["attached_servers"] = [{"name": wanted_server}]
        else:
            patch["attached_servers"] = []

    if patch:
        changed = True
        if not module.check_mode:
            res = blade.patch_network_interfaces(
                names=[module.params["name"]],
                network_interface=NetworkInterfacePatch(**patch),
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to modify Interface {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def delete_iface(module, blade):
    """Delete Network Interface"""
    changed = True
    if not module.check_mode:
        res = blade.delete_network_interfaces(names=[module.params["name"]])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete network {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def _check_versions(module, api_version):
    """Fail when an option needs a REST version the array does not have."""
    gates = (
        (
            module.params["attached_server"] is not None,
            "attached_server",
            SERVERS_API_VERSION,
        ),
        (module.params["services"] == "sts", "services sts", STS_API_VERSION),
        (
            module.params["services"] == "egress-only",
            "services egress-only",
            EGRESS_ONLY_API_VERSION,
        ),
        (module.params["rdma_enabled"] is not None, "rdma_enabled", RDMA_API_VERSION),
    )
    for used, option, minimum in gates:
        if used and LooseVersion(minimum) > LooseVersion(api_version):
            module.fail_json(
                msg="FlashBlade REST version {0} does not support {1} "
                "(requires {2}+).".format(api_version, option, minimum)
            )


def _check_options(module):
    """Refuse combinations the array rejects, before touching it."""
    services = module.params["services"]
    server = module.params["attached_server"]
    if module.params["rdma_enabled"] and services not in (None, "data"):
        module.fail_json(msg="rdma_enabled is only supported with the data service.")
    if services == "egress-only" and server:
        module.fail_json(msg="An egress-only interface cannot have an attached server.")
    if services == "sts" and server not in (None, "", DEFAULT_SERVER):
        module.fail_json(
            msg="An sts interface can only use the default server {0}.".format(
                DEFAULT_SERVER
            )
        )


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["present", "absent"]),
            address=dict(type="str"),
            services=dict(
                type="str", choices=["data", "replication", "egress-only", "sts"]
            ),
            itype=dict(type="str", default="vip", choices=["vip"]),
            attached_server=dict(type="str", required=False),
            rdma_enabled=dict(type="bool"),
        )
    )

    required_if = [["state", "present", ["address"]]]

    module = AnsibleModule(
        argument_spec, required_if=required_if, supports_check_mode=True
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")
    state = module.params["state"]
    blade = get_system(module)
    iface = get_iface(module, blade)

    api_version = get_rest_api_version(blade)
    if state == "present":
        _check_versions(module, api_version)
        _check_options(module)

    if state == "present" and not iface:
        create_iface(module, blade)
    elif state == "present" and iface:
        modify_iface(module, blade)
    elif state == "absent" and iface:
        delete_iface(module, blade)
    elif state == "absent" and not iface:
        module.exit_json(changed=False)


if __name__ == "__main__":
    main()
