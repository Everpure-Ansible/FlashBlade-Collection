#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2024, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_server
version_added: '1.20.0'
short_description: Manage FlashBlade servers
description:
- Add, update or delete FlashBlade servers
- Deleting a server also deletes the NFS directory service created with it.
  A local directory service attached to the server, including one created
  through I(create_local_directory_service), outlives the server and is
  removed with M(everpure.flashblade.purefb_local_ds).
- A server is not deleted while an object store virtual host is attached to
  it. A virtual host must stay attached to at least one object store server
  (Everpure support guidance for Purity//FB), so the delete is refused, in
  check mode as well, and the virtual hosts are named. Where the server is
  the only one attached to a virtual host, attach another server to that
  virtual host or delete the virtual host first. Then detach the server from
  every virtual host with M(everpure.flashblade.purefb_virtualhost) and
  delete it. The delete is also refused when the virtual hosts, or the
  servers attached to them, cannot be read. Applies from Purity//FB 4.6.3
  (REST 2.20), where virtual hosts have attached servers.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the server
    type: str
    required: true
  state:
    description:
    - Define whether the server should be added or deleted
    default: present
    choices: [ absent, present ]
    type: str
  dns:
    description:
    - The DNS configuration to be used for this server
    type: list
    elements: str
  directory_service:
    description:
    - The directory service configuration to be used for this server
    type: list
    elements: str
  local_directory_service:
    description:
    - Name of an existing local directory service to associate with this server
    - Set to an empty string (C("")) to clear a previously assigned local directory
      service. This only applies on update; on create an empty string is treated the
      same as omitting the parameter.
    - Mutually exclusive with I(create_local_directory_service).
    - Only valid with REST 2.24 or higher
    type: str
  create_local_directory_service:
    description:
    - Name of a local directory service for the array to create and associate
      with this server.
    - Only applies when the server is created. On an existing server the module
      checks that this is the local directory service attached and fails otherwise,
      since the array cannot create and attach one after the fact. Create it with
      M(everpure.flashblade.purefb_local_ds) and attach it with
      I(local_directory_service) instead.
    - The local directory service created this way is not deleted with the server.
      Remove it with M(everpure.flashblade.purefb_local_ds) after the server is gone.
    - Mutually exclusive with I(local_directory_service).
    - An empty string (C("")) is treated the same as omitting the parameter.
    - Only valid with REST 2.24 or higher
    type: str
    version_added: '1.30.0'
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Add server
  everpure.flashblade.purefb_server:
    name: myserver
    dns: mydns
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Add server and create its own local directory service
  everpure.flashblade.purefb_server:
    name: myserver
    create_local_directory_service: myserver_local
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Detach the server from a virtual host that keeps another server
  everpure.flashblade.purefb_virtualhost:
    name: acme-s3
    servers:
      - otherserver
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Delete server
  everpure.flashblade.purefb_server:
    name: myserver
    state: absent
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Clear local directory service
  everpure.flashblade.purefb_server:
    name: myserver
    local_directory_service: ""
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import Server, ServerPost, Reference
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

MIN_REQUIRED_API_VERSION = "2.16"
LOCAL_DS_API_VERSION = "2.24"
VHOST_SERVERS_API_VERSION = "2.20"
WILDCARD_SERVER = "*"


_UNSET = object()


def _field(obj, key, default=None):
    """Return a field of an SDK object or of a plain dict"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _reference_keys(ref):
    """Return the name and ID of a server or of a server reference"""
    return _field(ref, "name"), _field(ref, "id")


def _virtual_hosts_of_server(module, blade, servers):
    """Return the names of the object store virtual hosts attached to the
    servers the delete addresses: those with no other server attached, and
    those that are attached to other servers as well.

    The delete is only sent once it is known that no virtual host is
    attached, so the module stops when the virtual hosts or their attached
    servers cannot be read, and an attached server that cannot be identified
    counts as one of the servers to delete. The wildcard * is not a server
    and never counts as another one.

    ``servers`` is every server the lookup of the name returned. Server
    names are not case sensitive and a name holding a comma matches more
    than one server, so each of them is compared, by ID and by name.
    """
    name = module.params["name"]
    res = blade.get_object_store_virtual_hosts()
    if res.status_code != 200:
        module.fail_json(
            msg="Server {0} was not deleted: failed to list the object store "
            "virtual hosts to check that none is attached to it. "
            "Error: {1}".format(name, get_error_message(res))
        )
    names = set([name.lower()])
    ids = set()
    for server in servers:
        server_name, server_id = _reference_keys(server)
        if server_name:
            names.add(str(server_name).lower())
        if server_id:
            ids.add(server_id)
    sole = []
    shared = []
    unknown = []
    for vhost in list(res.items):
        refs = _field(vhost, "attached_servers", _UNSET)
        if refs is _UNSET:
            # The client speaks a REST version without attached servers
            unknown.append(str(_field(vhost, "name")))
            continue
        attached = False
        others = False
        for ref in refs or []:
            ref_name, ref_id = _reference_keys(ref)
            if ref_id is not None and ref_id in ids:
                attached = True
            elif ref_name is not None and str(ref_name).lower() in names:
                attached = True
            elif ref_name is None and (ref_id is None or not ids):
                attached = True
            elif ref_name != WILDCARD_SERVER:
                others = True
        if attached:
            (shared if others else sole).append(str(_field(vhost, "name")))
    if unknown:
        module.fail_json(
            msg="Server {0} was not deleted: the servers attached to the "
            "object store virtual hosts {1} are not reported to this client, "
            "so it cannot be checked that none of them is attached to the "
            "server. Use a py-pure-client release that supports REST {2} or "
            "higher.".format(
                name, ", ".join(sorted(unknown)), VHOST_SERVERS_API_VERSION
            )
        )
    return sorted(sole), sorted(shared)


def delete_server(module, blade, api_version, servers):
    """Delete server object, unless a virtual host is attached to it"""
    changed = True
    if LooseVersion(VHOST_SERVERS_API_VERSION) <= LooseVersion(api_version):
        # Neither the delete nor any change to a virtual host is sent while
        # a virtual host is attached to the server, whatever the array would
        # do with the attachment.
        sole, shared = _virtual_hosts_of_server(module, blade, servers)
        if sole or shared:
            msg = (
                "Server {0} was not deleted because it is attached to object "
                "store virtual hosts. A virtual host must stay attached to at "
                "least one object store server (Everpure support guidance "
                "for Purity//FB).".format(module.params["name"])
            )
            if sole:
                msg += (
                    " It is the only server attached to {0}: attach another "
                    "server to each of these virtual hosts and detach this "
                    "one, or delete them, first.".format(", ".join(sole))
                )
            if shared:
                msg += (
                    " It is attached along with other servers to {0}: detach "
                    "it from each of these virtual hosts with "
                    "purefb_virtualhost first.".format(", ".join(shared))
                )
            module.fail_json(msg=msg)
    if not module.check_mode:
        res = blade.delete_servers(
            names=[module.params["name"]], cascade_delete="directory-services"
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete server {0}. Error: {1}".format(
                    module.params["name"],
                    get_error_message(res),
                )
            )
    module.exit_json(changed=changed)


def update_server(module, blade):
    """Update server object"""
    changed = False
    server_info = list(blade.get_servers(names=[module.params["name"]]).items)[0]
    if module.params["create_local_directory_service"]:
        # create_local_directory_service is a create-time parameter; the array
        # cannot create and attach an LDS to a server that already exists.
        # Accept a matching attachment as idempotent, otherwise fail rather
        # than silently hiding the drift.
        current_lds = getattr(
            getattr(server_info, "local_directory_service", None), "name", None
        )
        if current_lds != module.params["create_local_directory_service"]:
            module.fail_json(
                msg="Server {0} already exists and its local directory service "
                "is {1}, not {2}. A local directory service can only be created "
                "with the server; create it with purefb_local_ds and attach it "
                "with local_directory_service instead.".format(
                    module.params["name"],
                    current_lds or "not set",
                    module.params["create_local_directory_service"],
                )
            )
    if module.params["dns"] is not None:
        dns_list = server_info.dns
        current_dns = []
        for dns in dns_list:
            current_dns.append(getattr(dns, "name", None))
        if set(module.params["dns"]) != set(current_dns):
            changed = True
            if not module.check_mode:
                res = blade.patch_servers(
                    names=[module.params["name"]],
                    server=Server(
                        dns=[Reference(name=d) for d in module.params["dns"]]
                    ),
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to update DNS config for server {0}. Error: {1}".format(
                            module.params["name"],
                            get_error_message(res),
                        )
                    )
    if module.params["directory_service"] is not None:
        ds_list = server_info.directory_services
        current_ds = []
        for ds in ds_list:
            current_ds.append(getattr(ds, "name", None))
        if set(module.params["directory_service"]) != set(current_ds):
            changed = True
            if not module.check_mode:
                res = blade.patch_servers(
                    names=[module.params["name"]],
                    server=Server(
                        directory_services=[
                            Reference(name=ds)
                            for ds in module.params["directory_service"]
                        ]
                    ),
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to update directory services for server {0}. Error: {1}".format(
                            module.params["name"],
                            get_error_message(res),
                        )
                    )
    if module.params["local_directory_service"] is not None:
        current_lds = getattr(
            getattr(server_info, "local_directory_service", None), "name", None
        )
        # normalise "" to None so clearing an already-unset field is a no-op
        if (module.params["local_directory_service"] or None) != current_lds:
            changed = True
            if not module.check_mode:
                res = blade.patch_servers(
                    names=[module.params["name"]],
                    server=Server(
                        local_directory_service=Reference(
                            name=module.params["local_directory_service"]
                        )
                    ),
                )
                if res.status_code != 200:
                    module.fail_json(
                        msg="Failed to update local directory service for server {0}. Error: {1}".format(
                            module.params["name"],
                            get_error_message(res),
                        )
                    )
    module.exit_json(changed=changed)


def add_server(module, blade):
    """Add server object"""
    changed = True
    final_dns = []
    final_dserv = []
    if not module.check_mode:
        if module.params["dns"]:
            for dns in module.params["dns"]:
                final_dns.append(Reference(name=dns))
        if module.params["directory_service"]:
            for dserv in module.params["directory_service"]:
                final_dserv.append(Reference(name=dserv))
        server_kwargs = {}
        if final_dns:
            server_kwargs["dns"] = final_dns
        if final_dserv:
            server_kwargs["directory_services"] = final_dserv
        if module.params["local_directory_service"]:
            server_kwargs["local_directory_service"] = Reference(
                name=module.params["local_directory_service"]
            )
        server = ServerPost(**server_kwargs)
        post_kwargs = {}
        if module.params["create_local_directory_service"]:
            # query parameter, never also set ServerPost.local_directory_service
            post_kwargs["create_local_directory_service"] = module.params[
                "create_local_directory_service"
            ]
        res = blade.post_servers(
            names=[module.params["name"]],
            server=server,
            create_ds=module.params["name"] + "_nfs",
            **post_kwargs
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to add server {0}. Error: {1}".format(
                    module.params["name"],
                    get_error_message(res),
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["absent", "present"]),
            name=dict(type="str", required=True),
            dns=dict(type="list", elements="str"),
            directory_service=dict(type="list", elements="str"),
            local_directory_service=dict(type="str"),
            create_local_directory_service=dict(type="str"),
        )
    )

    # The API refuses these two together: one names an existing local
    # directory service to attach, the other one to create with the server
    mutually_exclusive = [["local_directory_service", "create_local_directory_service"]]

    module = AnsibleModule(
        argument_spec,
        mutually_exclusive=mutually_exclusive,
        supports_check_mode=True,
    )
    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")
    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="FlashBlade REST version not supported. "
            "Minimum version required: {0}".format(MIN_REQUIRED_API_VERSION)
        )
    # local_directory_service treats "" as a request to clear the LDS on
    # update, so any given value needs the 2.24 API. For
    # create_local_directory_service "" is the same as omitting it, as in
    # add_server and update_server, so only a name trips the gate.
    lds_options_given = []
    if module.params["local_directory_service"] is not None:
        lds_options_given.append("local_directory_service")
    if module.params["create_local_directory_service"]:
        lds_options_given.append("create_local_directory_service")
    if lds_options_given and LooseVersion(LOCAL_DS_API_VERSION) > LooseVersion(
        api_version
    ):
        module.fail_json(
            msg="FlashBlade REST version {0} does not support "
            "{1} (requires {2} or higher).".format(
                api_version, lds_options_given[0], LOCAL_DS_API_VERSION
            )
        )
    state = module.params["state"]

    res = blade.get_servers(names=[module.params["name"]])
    exists = bool(res.status_code == 200)

    if not exists and state == "present":
        add_server(module, blade)
    elif exists and state == "present":
        update_server(module, blade)
    elif exists and state == "absent":
        delete_server(module, blade, api_version, list(res.items))

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
