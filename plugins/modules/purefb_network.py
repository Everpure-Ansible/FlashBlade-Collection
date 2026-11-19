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
    - An interface in a realm is named C(realm::name). Its subnet must first
      be shared with the realm using
      M(everpure.flashblade.purefb_resource_access).
    - To bring up an isolated realm, create an C(egress-only) interface in
      the realm first, point the realm's DNS at it with
      M(everpure.flashblade.purefb_dns), create the realm server with
      M(everpure.flashblade.purefb_server), then switch the interface to the
      C(data) service and attach the server. The interface, the DNS
      configuration and the server are all named with the realm, as
      C(realm::name). Tear down in the reverse order.
author: Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
      - Interface Name.
      - An interface in a realm is named C(realm::name). A name without a
        realm is an array-level interface. It is never completed with a
        realm, so an administrator whose access is limited to a realm must
        use the realm-qualified name.
      - This is the name of one interface. A name with a C(*) or a comma,
        which the array reads as a pattern or as a list of names, is
        refused.
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
        - An interface and its server must be in the same realm, or both
          outside of any realm. The server of an interface named
          C(realm-1::foo) is given as C(realm-1::server-1). A server named
          without a realm is looked up in the realm of the interface, so
          C(server-1) is the same server there. A server of another realm,
          and a server of a realm on an array-level interface, is refused.
        - Only 1 server per Network Interface.
        - An C(egress-only) interface cannot have a server. To attach one
          to such an interface, set I(services) to C(data) in the same task.
        - Set to an empty string to detach the interface from its server.
          The array keeps the default C(_array_server) on C(data) and C(sts)
          interfaces, so an empty string on those is the same as
          C(_array_server).
        - The default C(_array_server) is an array-level server and cannot
          be attached to an interface in a realm, so an interface in a
          realm has no default server. A C(data) interface in a realm
          therefore always names a server of its realm, and creating one,
          switching one to C(data) or detaching one without a server is
          refused. Use C(egress-only) for an interface in a realm that has
          no server.
        - A server that does not exist fails the task before anything is
          changed, in check mode as well.
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

- name: Create an egress-only interface in realm realm-1, on a subnet shared with that realm
  everpure.flashblade.purefb_network:
    name: realm-1::egress
    address: 10.21.200.24
    services: egress-only
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Switch the realm interface to the data service and attach a server of its realm
  everpure.flashblade.purefb_network:
    name: realm-1::egress
    address: 10.21.200.24
    services: data
    attached_server: realm-1::server-1
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a data interface named foo in realm realm-1 with attached server server-1 of that realm
  everpure.flashblade.purefb_network:
    name: realm-1::foo
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
REALMS_API_VERSION = "2.19"
RDMA_API_VERSION = "2.28"

DEFAULT_SERVER = "_array_server"


def _realm_of(name):
    """Return the realm of a realm::name name, empty for an array-level name."""
    return name.rpartition("::")[0]


def _same_name(first, second):
    """Tell whether two names are the same name on the array.

    The array matches a name without regard to case and to white space
    around it.
    """
    return first.strip().lower() == second.strip().lower()


def _single_name(module):
    """Refuse a name that the array does not read as the name of one interface.

    In a request the array reads * in a name as a pattern and a comma as a
    separator of names, so such a name reaches interfaces that only match
    it, or several at once. This module manages the one interface that has
    the name given, so the name is refused before anything is read.
    """
    name = module.params["name"]
    if "*" in name or "," in name:
        module.fail_json(
            msg="name must be the name of one network interface: in {0} the "
            "array reads * as a pattern and a comma as a separator of "
            "names.".format(name)
        )


def _is_missing(res, name):
    """Tell whether the answer to a look-up says that name does not exist.

    Only an answer without an object of that name, or the array's "does not
    exist", counts. An answer the array refuses or fails says nothing about
    the object, so it is not taken as missing.
    """
    if res.status_code == 200:
        return not [
            item
            for item in res.items
            if _same_name(str(getattr(item, "name", "")), name)
        ]
    return "does not exist" in str(get_error_message(res)).lower()


def get_iface(module, blade):
    """Return the interface called name, or None when it does not exist.

    Only the array's "does not exist" means that there is no such interface.
    Any other answer fails the task with the array's message: read as absent
    it would let state=absent report that there is nothing to delete, or
    state=present send a create for an interface that exists.
    """
    name = module.params["name"]
    res = blade.get_network_interfaces(names=[name])
    if res.status_code == 200:
        items = list(res.items)
        for item in items:
            if _same_name(str(getattr(item, "name", "")), name):
                return item
        if items:
            module.fail_json(
                msg="Failed to read Interface {0}: the array answered with "
                "{1}, which does not have that name.".format(
                    name,
                    ", ".join(str(getattr(item, "name", "")) for item in items[:5]),
                )
            )
        return None
    error = get_error_message(res)
    if "does not exist" in str(error).lower():
        return None
    module.fail_json(msg="Failed to read Interface {0}. Error: {1}".format(name, error))


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
    a change it cannot make. The array matches a server name without regard
    to case, so a name that differs only in case is the server in place.
    """
    current = current or ""
    if _same_name(wanted, current):
        return True
    if wanted == "":
        if "egress-only" in services:
            return True
        if current == DEFAULT_SERVER and ("data" in services or "sts" in services):
            return True
    return False


def _wanted_server(module, iface_name):
    """Return attached_server as the array names that server.

    For an interface in a realm the array looks a server named without a
    realm up in the realm of the interface, never at array level, and
    reports it as realm::server. A bare name is therefore completed with the
    realm of the interface, for the comparison and for the request, so that
    it is not reported as a change on every run and names the same server
    for every administrator. The default _array_server is the one name the
    array always reads as the array-level server, so it is never completed.
    None and "" are returned as given.
    """
    server = module.params["attached_server"]
    realm = _realm_of(iface_name)
    if (
        server
        and realm
        and "::" not in server
        and not _same_name(server, DEFAULT_SERVER)
    ):
        return "{0}::{1}".format(realm, server)
    return server


def _server_note(module, server):
    """Say how a bare attached_server was completed, for a failure message."""
    given = module.params["attached_server"]
    if given and server and server != given:
        return (
            " attached_server {0} was looked up as {1}, in the realm of the "
            "interface.".format(given, server)
        )
    return ""


def _check_server_scope(module, iface_name):
    """Fail when attached_server names a server outside the realm of the interface.

    The array attaches an interface in a realm only to a server of that
    realm and an array-level interface only to an array-level server. It
    refuses any other pair when the request is sent, which check mode cannot
    foresee, so such a pair is refused before anything is written. A server
    named without a realm is a server of the realm of the interface, see
    _wanted_server, except for the default _array_server, which is always
    the array-level server.
    """
    server = module.params["attached_server"]
    if not server:
        return
    realm = _realm_of(iface_name)
    if "::" in server:
        server_realm = _realm_of(server)
    elif _same_name(server, DEFAULT_SERVER):
        server_realm = ""
    else:
        return
    if _same_name(server_realm, realm):
        return
    if realm:
        reason = (
            "an interface in realm {0} takes a server of that realm, named "
            "{0}::<server>".format(realm)
        )
    else:
        reason = (
            "an array-level interface takes an array-level server, and an "
            "interface for this server is named {0}::<interface>".format(server_realm)
        )
    module.fail_json(
        msg="Cannot attach interface {0} to server {1}: {2}.".format(
            iface_name, server, reason
        )
    )


def _require_server(module, blade, server):
    """Fail when the server an interface is to be attached to does not exist.

    The array refuses the request for a server it does not have, which check
    mode cannot foresee, so the server is looked up before a change is
    reported. A look-up the array does not answer is left to the request.
    """
    if _is_missing(blade.get_servers(names=[server]), server):
        module.fail_json(
            msg="Cannot attach interface {0} to server {1}: the server does "
            "not exist.{2}".format(
                module.params["name"], server, _server_note(module, server)
            )
        )


def _require_realm(module, blade, api_version):
    """Fail when a new interface is named into a realm that does not exist.

    The array refuses such a create, which check mode cannot foresee, so
    the realm is looked up before a change is reported. A look-up the array
    does not answer is left to the create request.
    """
    name = module.params["name"]
    realm = _realm_of(name)
    if not realm or LooseVersion(REALMS_API_VERSION) > LooseVersion(api_version):
        return
    if _is_missing(blade.get_realms(names=[realm]), realm):
        module.fail_json(
            msg="Interface {0} cannot be created: realm {1} does not "
            "exist.".format(name, realm)
        )


def _refuse_data_without_server(module, iface_name):
    """Fail for a data interface in a realm that would have no server.

    The array hands a new or a detached array-level data interface to
    _array_server. An interface in a realm has no such default, and a data
    interface without a server is not supported there, so the request is
    refused before it is sent, in check mode as well.
    """
    module.fail_json(
        msg="Interface {0} would be a data interface without a server, which "
        "is not supported for an interface in a realm: set attached_server "
        "to a server of realm {1}, or use services egress-only for an "
        "interface without a server.".format(iface_name, _realm_of(iface_name))
    )


def create_iface(module, blade):
    """Create Network Interface"""
    changed = True
    name = module.params["name"]
    services = module.params["services"] or "data"
    server = _wanted_server(module, name)
    if _realm_of(name) and services == "data" and not server:
        _refuse_data_without_server(module, name)
    if server:
        _require_server(module, blade, server)
    if not module.check_mode:
        kwargs = dict(
            address=module.params["address"],
            services=[services],
            type=module.params["itype"],
        )
        # An empty attached_server is the array default (data falls back to
        # _array_server, everything else has none), so only a name is sent.
        if server:
            kwargs["attached_servers"] = [{"name": server}]
        if module.params["rdma_enabled"] is not None:
            kwargs["rdma_enabled"] = module.params["rdma_enabled"]
        res = blade.post_network_interfaces(
            names=[name],
            network_interface=NetworkInterface(**kwargs),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Interface {0} creation failed. Error: {1}{2}".format(
                    name, get_error_message(res), _server_note(module, server)
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
    # The realm is the one of the name the array holds, and a server named
    # without a realm is compared and sent as a server of that realm.
    wanted_server = _wanted_server(module, iface.name)
    current_server = _attached_server_name(iface)
    if wanted_server is not None and not _server_in_sync(
        wanted_server, current_server, wanted_services
    ):
        if wanted_server:
            patch["attached_servers"] = [{"name": wanted_server}]
        else:
            patch["attached_servers"] = []

    # The array refuses a server on an egress-only interface. main() checks
    # the pair when the task names the service. With services left out the
    # service of the interface decides, as it does for rdma_enabled above,
    # so the pair is refused here instead of being reported as a change.
    if patch.get("attached_servers") and "egress-only" in wanted_services:
        module.fail_json(
            msg="Interface {0} is an egress-only interface, which cannot have "
            "an attached server: set services to data in the same task to "
            "attach {1}.".format(iface.name, wanted_server)
        )

    # A data interface in a realm has no default server to fall back on, so
    # a task that detaches one, or switches one to data without a server, is
    # refused here instead of being reported as a change.
    if _realm_of(iface.name) and "data" in wanted_services:
        detached = "attached_servers" in patch and not patch["attached_servers"]
        unserved = "services" in patch and not wanted_server and not current_server
        if detached or unserved:
            _refuse_data_without_server(module, iface.name)
    note = ""
    if patch.get("attached_servers"):
        _require_server(module, blade, wanted_server)
        note = _server_note(module, wanted_server)

    if patch:
        changed = True
        if not module.check_mode:
            # Addressed by the name the array holds: it finds an interface
            # under a name in another case, but refuses to change one that
            # is addressed with its realm written in another case.
            res = blade.patch_network_interfaces(
                names=[iface.name],
                network_interface=NetworkInterfacePatch(**patch),
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to modify Interface {0}. Error: {1}{2}".format(
                        module.params["name"], get_error_message(res), note
                    )
                )
    module.exit_json(changed=changed)


def delete_iface(module, blade, name=None):
    """Delete Network Interface

    ``name`` is the name the array holds for the interface, which main()
    passes in so that the interface is addressed as the array names it.
    """
    changed = True
    if not module.check_mode:
        res = blade.delete_network_interfaces(names=[name or module.params["name"]])
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
    # Whatever the state, the task names one interface.
    _single_name(module)
    blade = get_system(module)
    iface = get_iface(module, blade)

    api_version = get_rest_api_version(blade)
    if state == "present":
        _check_versions(module, api_version)
        _check_options(module)
        _check_server_scope(module, iface.name if iface else module.params["name"])

    if state == "present" and not iface:
        _require_realm(module, blade, api_version)
        create_iface(module, blade)
    elif state == "present" and iface:
        modify_iface(module, blade)
    elif state == "absent" and iface:
        delete_iface(module, blade, iface.name)
    elif state == "absent" and not iface:
        module.exit_json(changed=False)


if __name__ == "__main__":
    main()
