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
- From Purity//FB 4.6.3 (REST 2.20) a virtual host is attached to object
  store servers. Following Everpure support guidance for Purity//FB a
  virtual host must stay attached to at least one object store server, so
  this module never creates a virtual host without an attached server and
  never detaches the last server from one. Use I(state=absent) to remove a
  virtual host.
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
      this list. New servers are attached before any other is detached.
    - A virtual host must stay attached to at least one object store
      server, so an empty list is refused. List the servers that should
      stay attached, or use I(state=absent) to remove the virtual host.
    - When omitted on creation the module attaches the default object
      store server. That is C(_array_server) for an array-scoped virtual
      host and the default object store server of the realm for a
      realm-scoped one (see I(default_object_server) of
      M(everpure.flashblade.purefb_realm)). The virtual host is not created
      when there is no default object store server.
    - When omitted for an existing virtual host the attached servers are
      left unchanged. An existing virtual host that has no attached server
      is not modified until I(servers) names a server to attach.
    - Requires Purity//FB 4.6.3 or higher (REST 2.20). Earlier versions
      have no attached servers and are not affected.
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
- name: Add Object Store Virtual Host attached to the default object store server
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

- name: Add realm-scoped Object Store Virtual Host attached to a server of the realm
  everpure.flashblade.purefb_virtualhost:
    name: "tenant1::acme-s3"
    hostname: "s3.tenant1.acme.com"
    servers:
      - "tenant1::s3srv"
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

# A virtual host must stay attached to at least one object store server, so
# an empty servers list is refused. List the servers that should stay
# attached, or delete the virtual host.
- name: Leave only tenant_a attached to an Object Store Virtual Host
  everpure.flashblade.purefb_virtualhost:
    name: "acme-s3"
    servers:
      - tenant_a
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
ARRAY_DEFAULT_SERVER = "_array_server"
WILDCARD_SERVER = "*"
# Everpure support guidance for Purity//FB. Every request this module sends
# is built so that the rule holds before, between and after the requests.
ATTACH_RULE = "A virtual host must stay attached to at least one object store server"


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


def _server_names(vhost):
    """Return the names of the servers attached to a virtual host as a set.

    A virtual host that reports no attached servers, or no attached_servers
    attribute at all, gives an empty set.
    """
    attached = getattr(vhost, "attached_servers", None) or []
    return set(
        srv_name
        for srv_name in (getattr(srv, "name", None) for srv in attached)
        if srv_name
    )


def _references(servers):
    """Return the server names as a list of references for a request body."""
    return [Reference(name=srv) for srv in servers]


def _validate_servers(module):
    """Refuse a servers list that names no server."""
    servers = module.params["servers"]
    if servers is None:
        return
    if not servers:
        module.fail_json(
            msg="servers cannot be an empty list for Object Store Virtual Host "
            "{0}. {1}: list the servers that should stay attached, or use "
            "state=absent to remove the virtual host.".format(
                module.params["name"], ATTACH_RULE
            )
        )
    if [srv for srv in servers if not str(srv).strip()]:
        module.fail_json(
            msg="servers cannot contain an empty server name for Object Store "
            "Virtual Host {0}. {1}.".format(module.params["name"], ATTACH_RULE)
        )


def _require_servers(module, blade, servers, ctx):
    """Fail unless every server named for a new virtual host exists.

    A virtual host is only created with servers the array is known to have,
    so the create request cannot end with nothing attached because a name
    did not resolve. The wildcard is not a server object and is left to the
    array.
    """
    names = [srv for srv in servers if srv != WILDCARD_SERVER]
    if not names:
        return
    res = blade.get_servers(names=names, **ctx)
    if res.status_code != 200:
        module.fail_json(
            msg="Object Store Virtual Host {0} was not created: servers {1} "
            "could not all be found. Error: {2}".format(
                module.params["name"], ", ".join(names), get_error_message(res)
            )
        )
    if len(list(res.items)) < len(names):
        module.fail_json(
            msg="Object Store Virtual Host {0} was not created: servers {1} "
            "could not all be found.".format(module.params["name"], ", ".join(names))
        )


def _default_server(module, blade, ctx):
    """Return the server a new virtual host is attached to when servers is
    not given, and fail when there is none.

    The array attaches its default object store server to a virtual host
    created without attached servers, and attaches nothing when no default
    is configured. The module therefore resolves the default itself and
    names it in the create request: _array_server for an array-scoped
    virtual host, the default object store server of the realm for a
    realm-scoped one.
    """
    name = module.params["name"]
    if "::" in name:
        realm = name.rsplit("::", 1)[0]
        res = blade.get_realms_defaults(realm_names=[realm], **ctx)
        if res.status_code != 200:
            module.fail_json(
                msg="Object Store Virtual Host {0} was not created: the default "
                "object store server of realm {1} could not be read. Pass "
                "servers with at least one server of the realm. Error: "
                "{2}".format(name, realm, get_error_message(res))
            )
        defaults = next(iter(res.items), None)
        object_store = getattr(defaults, "object_store", None) or []
        server = None
        if object_store:
            server = getattr(getattr(object_store[0], "server", None), "name", None)
        if not server:
            module.fail_json(
                msg="Object Store Virtual Host {0} was not created: realm {1} has "
                "no default object store server, so the virtual host would have "
                "no attached server. {2}. Pass servers with at least one server "
                "of the realm, or set the default object store server of the "
                "realm first (default_object_server of purefb_realm).".format(
                    name, realm, ATTACH_RULE
                )
            )
    else:
        server = ARRAY_DEFAULT_SERVER
    res = blade.get_servers(names=[server], **ctx)
    if res.status_code != 200 or not list(res.items):
        module.fail_json(
            msg="Object Store Virtual Host {0} was not created: the default "
            "object store server {1} was not found, so the virtual host would "
            "have no attached server. {2}. Pass servers with at least one "
            "server.".format(name, server, ATTACH_RULE)
        )
    return server


def _verify_created(module, blade, ctx):
    """Confirm a new virtual host has an attached server, else remove it.

    The create request always names at least one existing server, so this
    should never find anything wrong. If the read-back cannot confirm an
    attached server, the safest state is the one before the task: the
    virtual host was created by this task and nothing can depend on it yet,
    so it is deleted again rather than left for an attach that may never
    happen.
    """
    name = module.params["name"]
    vhost = _get_host(blade, name, ctx)
    if vhost is not None and _server_names(vhost):
        return
    res = blade.delete_object_store_virtual_hosts(names=[name], **ctx)
    if res.status_code == 200:
        module.fail_json(
            msg="Object Store Virtual Host {0} was created but an attached "
            "server could not be confirmed, so it was deleted again. "
            "{1}.".format(name, ATTACH_RULE)
        )
    module.fail_json(
        msg="Object Store Virtual Host {0} was created but an attached server "
        "could not be confirmed, and deleting it again failed. Attach a server "
        "to it or delete it. {1}. Error: {2}".format(
            name, ATTACH_RULE, get_error_message(res)
        )
    )


def _verify_attached(module, blade, ctx, previous, wanted):
    """Confirm a virtual host still has an attached server after a change.

    The requests sent by _change_servers cannot empty the attached set, so
    this should never find anything wrong. If the virtual host nevertheless
    reports no attached server, the servers it had before the task are
    attached again, because they are known to be attachable to it, and
    failing that the requested servers. An existing virtual host is never
    deleted by this repair: it was not created by this task, so removing it
    stays the operator's decision. The task fails in every case so that the
    result is noticed.
    """
    name = module.params["name"]
    vhost = _get_host(blade, name, ctx)
    if vhost is None:
        module.fail_json(
            msg="Object Store Virtual Host {0} could not be read back after its "
            "attached servers were changed. Check that it is attached to at "
            "least one object store server.".format(name)
        )
    if _server_names(vhost):
        return
    tried = []
    for candidate in (sorted(previous), sorted(wanted)):
        if not candidate or candidate in tried:
            continue
        tried.append(candidate)
        res = blade.patch_object_store_virtual_hosts(
            names=[name],
            object_store_virtual_host=ObjectStoreVirtualHostPatch(
                add_attached_servers=_references(candidate)
            ),
            **ctx
        )
        if res.status_code != 200:
            continue
        check = _get_host(blade, name, ctx)
        if check is not None and _server_names(check):
            module.fail_json(
                msg="Object Store Virtual Host {0} had no attached server after "
                "its attached servers were changed, so {1} was attached again. "
                "{2}. Check the virtual host and run the task again.".format(
                    name, ", ".join(candidate), ATTACH_RULE
                )
            )
    module.fail_json(
        msg="Object Store Virtual Host {0} has no attached server and attaching "
        "one again failed. Attach a server to it or delete it. {1}.".format(
            name, ATTACH_RULE
        )
    )


def _change_servers(module, blade, ctx, current, add, remove):
    """Attach and detach servers without ever emptying the attached set.

    New servers are attached in a first request and the others detached in
    a second one, so at least one server stays attached whatever order the
    array applies a request in and whichever request fails. Right before
    the detach the virtual host is read again, and the detach is only sent
    when a server remains attached after it. The result is then read back.
    """
    name = module.params["name"]
    if add:
        _patch_host(
            module,
            blade,
            ObjectStoreVirtualHostPatch(add_attached_servers=_references(add)),
            ctx,
            "update attached servers (attach {0})".format(", ".join(add)),
        )
    if remove:
        vhost = _get_host(blade, name, ctx)
        if vhost is None:
            module.fail_json(
                msg="Object Store Virtual Host {0} could not be read again "
                "before detaching {1}, so nothing was detached. Run the task "
                "again.".format(name, ", ".join(remove))
            )
        if not _server_names(vhost) - set(remove):
            module.fail_json(
                msg="Detaching {0} would leave Object Store Virtual Host {1} "
                "without an attached server, so nothing was detached. "
                "{2}.".format(", ".join(remove), name, ATTACH_RULE)
            )
        _patch_host(
            module,
            blade,
            ObjectStoreVirtualHostPatch(remove_attached_servers=_references(remove)),
            ctx,
            "update attached servers (detach {0})".format(", ".join(remove)),
        )
    _verify_attached(
        module, blade, ctx, current, (set(current) | set(add)) - set(remove)
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
    name = module.params["name"]
    hostname = module.params["hostname"]
    servers = module.params["servers"]
    if LooseVersion(SERVER_API_VERSION) > LooseVersion(api_version):
        # Before REST 2.20 a virtual host has no attached servers: the name
        # is the hostname and nothing else can be sent.
        if not module.check_mode:
            res = blade.post_object_store_virtual_hosts(names=[name], **ctx)
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to add Object Store Virtual Host {0}. Error: {1}".format(
                        name, get_error_message(res)
                    )
                )
        module.exit_json(changed=changed)

    # The create request always names the servers to attach, so the result
    # never depends on a default the array may not have. Every refusal
    # below happens before the request, in check mode as well.
    _validate_servers(module)
    if servers is None:
        servers = [_default_server(module, blade, ctx)]
    else:
        servers = [srv for pos, srv in enumerate(servers) if srv not in servers[:pos]]
        _require_servers(module, blade, servers, ctx)
    if not servers:
        # Not reachable: the last check before the request is built.
        module.fail_json(
            msg="Object Store Virtual Host {0} was not created. {1}.".format(
                name, ATTACH_RULE
            )
        )
    if not module.check_mode:
        body = {"attached_servers": _references(servers)}
        if hostname is not None:
            body["hostname"] = hostname
        res = blade.post_object_store_virtual_hosts(
            names=[name],
            object_store_virtual_host=ObjectStoreVirtualHost(**body),
            **ctx
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to add Object Store Virtual Host {0}. Error: {1}".format(
                    name, get_error_message(res)
                )
            )
        _verify_created(module, blade, ctx)
    module.exit_json(changed=changed)


def update_host(module, blade, vhost, api_version, ctx):
    """Modify attached servers, hostname and name of an existing virtual host"""
    changed = False
    name = module.params["name"]
    hostname = module.params["hostname"]
    servers = module.params["servers"]
    rename = module.params["rename"]
    # Before REST 2.20 the name is the hostname
    current_hostname = getattr(vhost, "hostname", None) or vhost.name
    current_servers = _server_names(vhost)

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

    new_hostname = hostname is not None and hostname != current_hostname
    new_name = bool(rename and rename != name)
    add = []
    remove = []
    # Attached servers exist from REST 2.20; before it there is nothing to
    # guard and none of hostname, servers and rename can be given.
    if LooseVersion(SERVER_API_VERSION) <= LooseVersion(api_version):
        _validate_servers(module)
        if WILDCARD_SERVER in current_servers:
            if servers is not None:
                # The wildcard pseudo-server is not attachable or detachable
                module.warn(
                    "Object Store Virtual Host {0} is attached to all servers (*); "
                    "attached servers are not managed".format(name)
                )
        else:
            if servers is not None:
                wanted = set(servers)
                # Attaching an already attached server, or detaching one
                # that is not attached, is rejected by the array, so only
                # the exact delta is sent. attached_servers (full replace)
                # must never be combined with the add/remove lists.
                add = sorted(wanted - current_servers)
                remove = sorted(current_servers - wanted)
            # Every refusal happens here, before any request and in check
            # mode as well.
            if not current_servers and not add:
                if new_hostname or new_name:
                    module.fail_json(
                        msg="Object Store Virtual Host {0} has no attached server "
                        "and is not modified until one is attached. {1}: name a "
                        "server to attach with servers, or use state=absent to "
                        "remove the virtual host.".format(name, ATTACH_RULE)
                    )
                module.warn(
                    "Object Store Virtual Host {0} has no attached server. {1}: "
                    "name a server to attach with servers, or use state=absent "
                    "to remove the virtual host.".format(name, ATTACH_RULE)
                )
            elif not (current_servers | set(add)) - set(remove):
                module.fail_json(
                    msg="Detaching {0} would leave Object Store Virtual Host {1} "
                    "without an attached server. {2}: list the servers that "
                    "should stay attached, or use state=absent to remove the "
                    "virtual host.".format(", ".join(remove), name, ATTACH_RULE)
                )

    # Servers first, so that no later request is sent for a virtual host
    # that has no attached server.
    if add or remove:
        changed = True
        if not module.check_mode:
            _change_servers(module, blade, ctx, current_servers, add, remove)

    if new_hostname:
        changed = True
        if not module.check_mode:
            _patch_host(
                module,
                blade,
                ObjectStoreVirtualHostPatch(hostname=hostname),
                ctx,
                "set hostname",
            )

    if new_name:
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
        update_host(module, blade, vhost, api_version, ctx)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
