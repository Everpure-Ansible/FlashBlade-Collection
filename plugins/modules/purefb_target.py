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
module: purefb_target
version_added: '1.0.0'
short_description: Manage remote S3-capable targets for a FlashBlade
description:
- Manage remote S3-capable targets for a FlashBlade system
- Use this for non-FlashBlade targets.
- Use I(everpure.flashblade.purefb_connect) for FlashBlade targets.
- Targets are array-level objects. A target cannot be created in a realm,
  so the module refuses to create one under a realm-qualified name
  (C(realm::name)).
- To use a target for the buckets of a realm, share it with the realm using
  M(everpure.flashblade.purefb_resource_access) with I(resource_type=targets)
  and I(scope_type=realms). The remote credentials and the bucket replica
  links of the realm can name the target once it is shared.
- A network interface with the replication service is required to create a
  target.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Create or delete remote target
    default: present
    type: str
    choices: [ absent, present ]
  name:
    description:
    - Name of the S3-capable target
    - Targets are array-level objects, so the name cannot be realm-qualified
      (C(realm::name)).
    - The array matches the name of a target without regard to letter case.
    type: str
    required: true
  address:
    description:
    - Address of S3-capable target (IP or FQDN)
    - Required when I(state=present).
    type: str
notes:
- An administrator whose management access is limited to a realm sees the
  targets that are shared with that realm and no replication network
  interface. For such an administrator the module reports a shared target as
  it is and cannot create a target. Purity//FB 4.8 refuses that administrator
  a change of the address with C(Operation not permitted), which check mode
  cannot foresee.
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create a connection to remote S3-capable target
  everpure.flashblade.purefb_target:
    name: target_1
    address: 10.10.10.20
    fb_url: 10.10.10.2
    api_token: T-89faa581-c668-483d-b77d-23c5d88ba35c
- name: Share the target with a realm for its remote credentials and bucket replica links
  everpure.flashblade.purefb_resource_access:
    resource_type: targets
    resource_name: target_1
    scope_type: realms
    scope_name: realm1
    fb_url: 10.10.10.2
    api_token: T-89faa581-c668-483d-b77d-23c5d88ba35c
- name: Delete connection to remote S3-capable system
  everpure.flashblade.purefb_target:
    state: absent
    name: target_1
    fb_url: 10.10.10.2
    api_token: T-89faa581-c668-483d-b77d-23c5d88ba35c
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import TargetPost, Target
except ImportError:
    HAS_PYPURECLIENT = False

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_error_message,
)

REALM_NAME_MSG = (
    "Target {0} cannot be created: targets are array-level objects and their "
    "names cannot be realm-qualified (realm::name). Create the target under "
    "an unqualified name and share it with the realm using the "
    "purefb_resource_access module (resource_type targets, scope_type realms)."
)

NO_INTERFACE_MSG = (
    "Replication network interface required to create a target and none is "
    "visible to this user. Targets are array-level objects: an array "
    "administrator creates the target and can share it with a realm using "
    "the purefb_resource_access module (resource_type targets, scope_type "
    "realms)."
)


def _refuse_realm_name(module):
    """Refuse to create a target under a realm-qualified name, before any request

    Targets are array-level objects. The name rule of the array rejects the
    realm separator with a message that does not mention realms, and only on
    the real run, so check mode would report a change that cannot happen.
    Such a name never matches a target, so state=absent stays a no-op.
    """
    name = module.params["name"]
    if module.params["state"] == "present" and "::" in name:
        module.fail_json(msg=REALM_NAME_MSG.format(name))


def _get_targets(module, blade):
    """Return the targets the array lists for this user

    A read that the array refuses or fails is reported with the message of
    the array rather than taken for an array without targets.
    """
    res = blade.get_targets()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read the targets. Error: {0}".format(get_error_message(res))
        )
    return list(res.items)


def _find_target(targets, name):
    """Return the target called name, or None when there is none

    The array matches names without regard to letter case and keeps the
    spelling a target was created with, so the comparison ignores case and
    the requests that follow use the name the array returned.
    """
    for target in targets:
        if target.name.lower() == name.lower():
            return target
    return None


def _check_replication_configured(module, blade):
    """Fail unless a network interface with the replication service is visible

    Only the creation of a target depends on it. An administrator whose
    access is limited to a realm sees no such interface.
    """
    res = blade.get_network_interfaces()
    if res.status_code != 200:
        module.fail_json(
            msg="Failed to read the network interfaces. Error: {0}".format(
                get_error_message(res)
            )
        )
    for link in res.items:
        if "replication" in (link.services or []):
            return
    module.fail_json(msg=NO_INTERFACE_MSG)


def _check_address_unused(module, targets, connection=None):
    """Fail when a target other than connection has the requested address"""
    for target in targets:
        if connection is not None and target.name == connection.name:
            continue
        if target.address == module.params["address"]:
            module.fail_json(msg="Target already exists with same connection address")


def break_connection(module, blade, connection):
    """Break connection to remote target"""
    changed = True
    if not module.check_mode:
        res = blade.delete_targets(names=[connection.name])
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to disconnect target {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def create_connection(module, blade, targets):
    """Create connection to remote target"""
    changed = True
    _check_replication_configured(module, blade)
    _check_address_unused(module, targets)
    if not module.check_mode:
        target = TargetPost(address=module.params["address"])
        res = blade.post_targets(names=[module.params["name"]], target=target)
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to connect to remote target {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def update_connection(module, blade, connection, targets):
    """Update target connection address"""
    changed = False
    _check_address_unused(module, targets, connection)
    if module.params["address"] != connection.address:
        changed = True
        if not module.check_mode:
            new_address = Target(address=module.params["address"])
            res = blade.patch_targets(names=[connection.name], target=new_address)
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to change address for target {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["absent", "present"]),
            name=dict(type="str", required=True),
            address=dict(type="str"),
        )
    )

    required_if = [["state", "present", ["address"]]]

    module = AnsibleModule(
        argument_spec, required_if=required_if, supports_check_mode=True
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    state = module.params["state"]
    _refuse_realm_name(module)
    blade = get_system(module)
    targets = _get_targets(module, blade)
    target = _find_target(targets, module.params["name"])
    if state == "present" and not target:
        create_connection(module, blade, targets)
    elif state == "present" and target:
        update_connection(module, blade, target, targets)
    elif state == "absent" and target:
        break_connection(module, blade, target)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
