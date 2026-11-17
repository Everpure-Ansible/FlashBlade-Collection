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
module: purefb_virtualhost
version_added: '1.6.0'
short_description: Manage FlashBlade Object Store Virtual Hosts
description:
- Add, modify or delete FlashBlade Object Store Virtual Hosts
- A FlashBlade supports a maximum of 10 Object Store Virtual Hosts.
- The built-in I(s3.amazonaws.com) virtual host cannot be deleted or
  modified by this module.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the Object Store Virtual Host
    - Before REST 2.20 the name is also the hostname or domain by which the
      array can be addressed for virtual hosted-style S3 requests.
    - A realm-scoped virtual host is named C(realm::host). Such a name
      cannot contain dots and the array requires I(hostname) for it.
    type: str
    required: true
  hostname:
    description:
    - Hostname by which the array can be addressed for virtual hosted-style
      S3 requests.
    - Cannot exceed 255 characters, cannot be an IP address, and cannot be a
      superset or subset of an existing hostname with the same root.
    - When omitted on creation of an array-scoped virtual host the array
      sets the hostname to I(name). The array requires a hostname for
      realm-scoped virtual hosts.
    - Requires Purity//FB 4.6.3 or higher (REST 2.20).
    type: str
    version_added: '1.30.0'
  servers:
    description:
    - Exact list of object store servers allowed to use this virtual host.
    - Servers are attached and detached so that the attached set matches
      this list. An empty list detaches every server.
    - When omitted on creation the array attaches the default object store
      server. When omitted for an existing virtual host the attached servers
      are left unchanged.
    - Requires Purity//FB 4.6.3 or higher (REST 2.20).
    type: list
    elements: str
    version_added: '1.30.0'
  rename:
    description:
    - New name for the Object Store Virtual Host.
    - When no virtual host called I(name) exists but one called I(rename)
      does, the rename is treated as already done and the host is managed
      under its new name, so a rename task can be re-run.
    - Requires Purity//FB 4.6.3 or higher (REST 2.20).
    type: str
    version_added: '1.30.0'
  state:
    description:
    - Define whether the Object Store Virtual Host should be added or deleted
    default: present
    choices: [ absent, present ]
    type: str
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    type: str
    default: ""
    version_added: "1.22.0"
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Add Object Store Virtual Host
  everpure.flashblade.purefb_virtualhost:
    name: "s3.acme.com"
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Add Object Store Virtual Host with a hostname and explicit servers
  everpure.flashblade.purefb_virtualhost:
    name: "acme-s3"
    hostname: "s3.acme.com"
    servers:
      - tenant_a
      - tenant_b
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Detach all servers from an Object Store Virtual Host
  everpure.flashblade.purefb_virtualhost:
    name: "acme-s3"
    servers: []
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Rename Object Store Virtual Host
  everpure.flashblade.purefb_virtualhost:
    name: "acme-s3"
    rename: "acme-object"
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Delete Object Store Virtual Host
  everpure.flashblade.purefb_virtualhost:
    name: "nohost.acme.com"
    state: absent
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        ObjectStoreVirtualHost,
        ObjectStoreVirtualHostPatch,
        Reference,
    )
except ImportError:
    HAS_PYPURECLIENT = False

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

MAX_HOST_COUNT = 10
CONTEXT_API_VERSION = "2.17"
SERVER_API_VERSION = "2.20"
RESERVED_HOST = "s3.amazonaws.com"


def _context_kwargs(module, api_version):
    """Return context_names kwargs when a fleet context applies."""
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and module.params["context"]
    ):
        return {"context_names": [module.params["context"]]}
    return {}


def _get_host(blade, name, ctx):
    """Return the virtual host object for name, or None when it is absent."""
    res = blade.get_object_store_virtual_hosts(names=[name], **ctx)
    if res.status_code == 200:
        items = list(res.items)
        if items:
            return items[0]
    return None


def _patch_host(module, blade, body, ctx, what):
    """PATCH the virtual host and fail with the array error on a non-200."""
    res = blade.patch_object_store_virtual_hosts(
        names=[module.params["name"]], object_store_virtual_host=body, **ctx
    )
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to {0} for Object Store Virtual Host {1}. Error: {2}".format(
                what, module.params["name"], get_error_message(res)
            )
        )


def delete_host(module, blade, ctx):
    """Delete Object Store Virtual Host"""
    changed = False
    if module.params["name"] == RESERVED_HOST:
        module.warn(
            "{0} is a reserved name and cannot be deleted".format(RESERVED_HOST)
        )
    else:
        changed = True
        if not module.check_mode:
            res = blade.delete_object_store_virtual_hosts(
                names=[module.params["name"]], **ctx
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to delete Object Store Virtual Host {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def add_host(module, blade, api_version, ctx):
    """Add Object Store Virtual Host"""
    changed = True
    hostname = module.params["hostname"]
    servers = module.params["servers"]
    if not module.check_mode:
        if LooseVersion(SERVER_API_VERSION) <= LooseVersion(api_version) and (
            hostname is not None or servers is not None
        ):
            body = {}
            if hostname is not None:
                body["hostname"] = hostname
            if servers is not None:
                body["attached_servers"] = [Reference(name=srv) for srv in servers]
            res = blade.post_object_store_virtual_hosts(
                names=[module.params["name"]],
                object_store_virtual_host=ObjectStoreVirtualHost(**body),
                **ctx
            )
        else:
            # Without hostname or servers the array sets hostname=name and
            # attaches the default object store server itself.
            res = blade.post_object_store_virtual_hosts(
                names=[module.params["name"]], **ctx
            )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to add Object Store Virtual Host {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def update_host(module, blade, vhost, ctx):
    """Modify hostname, attached servers and name of an existing virtual host"""
    changed = False
    name = module.params["name"]
    hostname = module.params["hostname"]
    servers = module.params["servers"]
    rename = module.params["rename"]
    # Before REST 2.20 the name is the hostname
    current_hostname = getattr(vhost, "hostname", None) or vhost.name
    attached = getattr(vhost, "attached_servers", None) or []
    current_servers = set(
        srv_name
        for srv_name in (getattr(srv, "name", None) for srv in attached)
        if srv_name is not None
    )

    if name == RESERVED_HOST:
        if (
            (hostname is not None and hostname != current_hostname)
            or (servers is not None and set(servers) != current_servers)
            or (rename and rename != name)
        ):
            module.warn(
                "{0} is a reserved name and cannot be modified".format(RESERVED_HOST)
            )
        module.exit_json(changed=False)

    if hostname is not None and hostname != current_hostname:
        changed = True
        if not module.check_mode:
            _patch_host(
                module,
                blade,
                ObjectStoreVirtualHostPatch(hostname=hostname),
                ctx,
                "set hostname",
            )

    if servers is not None:
        if "*" in current_servers:
            # The wildcard pseudo-server is not attachable or detachable
            module.warn(
                "Object Store Virtual Host {0} is attached to all servers (*); "
                "attached servers are not managed".format(name)
            )
        else:
            wanted = set(servers)
            add = sorted(wanted - current_servers)
            remove = sorted(current_servers - wanted)
            # Attaching an already attached server, or detaching one that
            # is not attached, is rejected by the array, so only the exact
            # delta is sent. attached_servers (full replace) must never be
            # combined with the add/remove lists.
            if add or remove:
                changed = True
                if not module.check_mode:
                    body = {}
                    if add:
                        body["add_attached_servers"] = [
                            Reference(name=srv) for srv in add
                        ]
                    if remove:
                        body["remove_attached_servers"] = [
                            Reference(name=srv) for srv in remove
                        ]
                    _patch_host(
                        module,
                        blade,
                        ObjectStoreVirtualHostPatch(**body),
                        ctx,
                        "update attached servers",
                    )

    if rename and rename != name:
        changed = True
        if not module.check_mode:
            _patch_host(
                module,
                blade,
                ObjectStoreVirtualHostPatch(name=rename),
                ctx,
                "rename to {0}".format(rename),
            )

    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["absent", "present"]),
            name=dict(type="str", required=True),
            hostname=dict(type="str"),
            servers=dict(type="list", elements="str"),
            rename=dict(type="str"),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(SERVER_API_VERSION) > LooseVersion(api_version) and (
        module.params["hostname"] is not None
        or module.params["servers"] is not None
        or module.params["rename"]
    ):
        module.fail_json(
            msg="hostname, servers and rename require FlashBlade REST {0} "
            "(Purity//FB 4.6.3) or higher".format(SERVER_API_VERSION)
        )
    if (
        LooseVersion(CONTEXT_API_VERSION) <= LooseVersion(api_version)
        and not module.params["context"]
    ):
        # If no context is provided set the context to the local array name
        fleet_res = blade.get_fleets()
        if fleet_res.status_code == 200 and list(fleet_res.items):
            module.params["context"] = list(blade.get_arrays().items)[0].name
    ctx = _context_kwargs(module, api_version)
    state = module.params["state"]

    vhost = _get_host(blade, module.params["name"], ctx)
    if vhost is None and state == "present" and module.params["rename"]:
        # The rename may already have happened on an earlier run: if a host
        # with the new name exists, manage it under that name and treat the
        # rename as done, so a repeated rename task still converges.
        renamed = _get_host(blade, module.params["rename"], ctx)
        if renamed is not None:
            module.params["name"] = module.params["rename"]
            module.params["rename"] = None
            vhost = renamed
    if vhost and state == "absent":
        delete_host(module, blade, ctx)
    elif not vhost and state == "present":
        # The host cap only limits additions; deleting, or re-asserting a
        # host that already exists, must not be blocked by it.
        vhosts = blade.get_object_store_virtual_hosts(**ctx)
        if vhosts.total_item_count >= MAX_HOST_COUNT:
            module.fail_json(
                msg="Maximum Object Store Virtual Host count ({0}) reached. "
                "Cannot add {1}.".format(MAX_HOST_COUNT, module.params["name"])
            )
        add_host(module, blade, api_version, ctx)
    elif vhost and state == "present":
        update_host(module, blade, vhost, ctx)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
