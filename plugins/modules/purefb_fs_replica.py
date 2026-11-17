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


DOCUMENTATION = """
---
module: purefb_fs_replica
version_added: '1.0.0'
short_description:  Manage filesystem replica links between Everpure FlashBlades
description:
    - This module manages filesystem replica links between Everpure FlashBlades.
author: Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
      - Local Filesystem Name.
    required: true
    type: str
  state:
    description:
      - Creates or modifies a filesystem replica link.
      - With I(state=absent) and I(policy) set, the policy is removed from
        the replica link. Without I(policy) the replica link itself is
        deleted (requires REST 2.10 or higher).
    required: false
    default: present
    type: str
    choices: [ "present", "absent" ]
  target_array:
    description:
      - Remote array name to create replica on.
      - When the local filesystem replicates to several arrays (fan-out),
        this selects the replica link the module acts on.
    required: false
    type: str
  target_fs:
    description:
      - Name of target filesystem name
      - If not supplied, will default to I(name).
    type: str
    required: false
  policy:
    description:
      - Name of filesystem snapshot policy to apply to the replica link.
      - Policies cannot be attached to C(partial-replica) links.
    required: false
    type: str
  in_progress:
    description:
     - Confirmation that you wish to delete a filesystem replica link
     - This may cancel any in-progress replication transfers)
    type: bool
    default: false
  link_type:
    description:
      - Type of replica link to create.
      - C(full-replica) replicates whole snapshots to the target.
        C(partial-replica) is a rapid file replication link that replicates
        metadata and transfers file data on demand.
      - When omitted the array creates a C(full-replica) link.
      - The type of an existing link cannot be changed; specifying a
        different type for an existing link fails.
      - A C(partial-replica) link cannot carry policies and cannot be deleted
        with I(state=absent); the array removes it when the replica
        filesystem on the target array is destroyed and eradicated.
      - Requires REST 2.17 or higher.
    type: str
    choices: [ "full-replica", "partial-replica" ]
    version_added: '1.30.0'
  replicate_now:
    description:
      - Trigger an immediate synchronisation of an existing C(partial-replica)
        link to I(target_array).
      - This is an action, not a state; the module always reports a change
        and performs nothing in check mode.
      - Requires REST 2.17 or higher.
    type: bool
    default: false
    version_added: '1.30.0'
  remote_default_exports:
    description:
      - Protocols for which the array creates default exports on the array
        level default server for the remote filesystem when the link is
        created. The NFS export uses the rules C(*(rw,no_root_squash)) and
        the SMB export the default policies.
      - An empty list creates no default exports. When omitted the array
        creates both NFS and SMB exports.
      - Only used when the link is created; the array does not report the
        value afterwards, so it is not compared on an existing link.
      - Requires REST 2.25 or higher.
    type: list
    elements: str
    choices: [ "nfs", "smb" ]
    version_added: '1.30.0'
extends_documentation_fragment:
    - everpure.flashblade.everpure.fb
"""

EXAMPLES = """
- name: Create new filesystem replica from foo to bar on arrayB
  everpure.flashblade.purefb_fs_replica:
    name: foo
    target_array: arrayB
    target_fs: bar
    policy: daily
    state: present
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a replica link without default exports on the remote filesystem
  everpure.flashblade.purefb_fs_replica:
    name: foo
    target_array: arrayB
    remote_default_exports: []
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a partial-replica (rapid file replication) link with an NFS export only
  everpure.flashblade.purefb_fs_replica:
    name: foo
    target_array: arrayB
    link_type: partial-replica
    remote_default_exports:
      - nfs
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Synchronise the partial-replica link from foo to arrayB now
  everpure.flashblade.purefb_fs_replica:
    name: foo
    target_array: arrayB
    replicate_now: true
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Add new snapshot policy to exisitng filesystem replica link
  everpure.flashblade.purefb_fs_replica:
    name: foo
    policy: weekly
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete snapshot policy from filesystem replica foo
  everpure.flashblade.purefb_fs_replica:
    name: foo
    policy: weekly
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete the filesystem replica link for foo
  everpure.flashblade.purefb_fs_replica:
    name: foo
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = """
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import FileSystemReplicaLink, LocationReference
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

DELETE_RL_API_VERSION = "2.10"
LINK_TYPE_API_VERSION = "2.17"
REMOTE_EXPORTS_API_VERSION = "2.25"
PARTIAL_REPLICA = "partial-replica"


def get_local_fs(module, blade):
    """Return Filesystem or None"""
    res = blade.get_file_systems(names=[module.params["name"]])
    if res.status_code == 200:
        items = list(res.items)
        if items:
            return items[0]
    return None


def get_local_rl(module, blade):
    """Return the Filesystem Replica Link to act on, or None.

    A filesystem can replicate to several arrays (fan-out). When target_array
    is given, only the link to that array counts; otherwise the first link
    is used, as before.
    """
    res = blade.get_file_system_replica_links(
        local_file_system_names=[module.params["name"]]
    )
    if res.status_code != 200:
        return None
    links = list(res.items)
    if not links:
        return None
    target = module.params["target_array"]
    if not target:
        return links[0]
    for link in links:
        if link.remote.name == target:
            return link
    # target_array may be the management address rather than the array name
    remote_array = _check_connected(module, blade)
    if remote_array:
        for link in links:
            if link.remote.name == remote_array.remote.name:
                return link
    return None


def _rl_has_policy(module, blade, link):
    """Return True if the policy is attached to the replica link."""
    res = blade.get_file_system_replica_links_policies(
        local_file_system_names=[module.params["name"]],
        policy_names=[module.params["policy"]],
        remote_names=[link.remote.name],
    )
    if res.status_code != 200:
        return False
    return bool(list(res.items))


def _check_connected(module, blade):
    res = blade.get_array_connections()
    connected_blades = list(res.items)
    for target in connected_blades:
        if (
            target.remote.name == module.params["target_array"]
            or target.management_address == module.params["target_array"]
        ) and target.status in [
            "connected",
            "connecting",
            "partially_connected",
        ]:
            return target
    return None


def _remote_default_exports(exports):
    """Encode the remote_default_exports query parameter.

    The array wants the literal quoted empty string to create no default
    exports: an empty list (or a bare empty string) is serialised as an
    empty parameter and rejected with "Missing or invalid parameter".
    """
    if not exports:
        return ['""']
    return [protocol for protocol in ("nfs", "smb") if protocol in exports]


def create_rl(module, blade):
    """Create Filesystem Replica Link"""
    changed = True
    if not module.params["target_array"]:
        module.fail_json(msg="target_array is required to create a replica link.")
    # Validate the target connection before the check-mode exit so that a
    # check-mode run fails the same way the real run would.
    remote_array = _check_connected(module, blade)
    if not remote_array:
        module.fail_json(
            msg="Target array {0} is not connected".format(
                module.params["target_array"]
            )
        )
    if not module.check_mode:
        if not module.params["target_fs"]:
            module.params["target_fs"] = module.params["name"]
        link_body = {}
        if module.params["link_type"]:
            link_body["link_type"] = module.params["link_type"]
        if module.params["policy"]:
            link_body["policies"] = [LocationReference(name=module.params["policy"])]
        post_kwargs = {
            "local_file_system_names": [module.params["name"]],
            "remote_file_system_names": [module.params["target_fs"]],
            "remote_names": [remote_array.remote.name],
            "file_system_replica_link": FileSystemReplicaLink(**link_body),
        }
        if module.params["remote_default_exports"] is not None:
            post_kwargs["remote_default_exports"] = _remote_default_exports(
                module.params["remote_default_exports"]
            )
        res = blade.post_file_system_replica_links(**post_kwargs)
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create filesystem replica link for {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=changed)


def replicate_rl(module, blade, link):
    """Trigger an immediate synchronisation of a partial-replica link"""
    changed = True
    if not module.check_mode:
        res = blade.patch_file_system_replica_links(
            local_file_system_names=[module.params["name"]],
            remote_names=[link.remote.name],
            replicate_now=True,
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to replicate {0} to {1} now. Error: {2}".format(
                    module.params["name"],
                    link.remote.name,
                    get_error_message(res),
                )
            )
    module.exit_json(changed=changed)


def add_rl_policy(module, blade, link):
    """Add Policy to Filesystem Replica Link"""
    changed = False
    remote_name = link.remote.name
    if not _rl_has_policy(module, blade, link):
        changed = True
        if not module.check_mode:
            res = blade.post_file_system_replica_links_policies(
                policy_names=[module.params["policy"]],
                local_file_system_names=[module.params["name"]],
                remote_names=[remote_name],
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to add policy {0} to replica link {1}. Error: {2}".format(
                        module.params["policy"],
                        module.params["name"],
                        get_error_message(res),
                    )
                )
    module.exit_json(changed=changed)


def delete_rl_policy(module, blade, link):
    """Delete Policy from Filesystem Replica Link"""
    changed = False
    remote_name = link.remote.name
    if _rl_has_policy(module, blade, link):
        changed = True
        if not module.check_mode:
            res = blade.delete_file_system_replica_links_policies(
                policy_names=[module.params["policy"]],
                local_file_system_names=[module.params["name"]],
                remote_names=[remote_name],
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to remove policy {0} from replica link {1}. Error: {2}".format(
                        module.params["policy"],
                        module.params["name"],
                        get_error_message(res),
                    )
                )
    module.exit_json(changed=changed)


def delete_rl(module, blade, link):
    """Delete filesystem replica link"""
    changed = True
    remote_name = link.remote.name
    remote_fs = link.remote_file_system.name
    if not module.check_mode:
        res = blade.delete_file_system_replica_links(
            local_file_system_names=[module.params["name"]],
            remote_file_system_names=[remote_fs],
            remote_names=[remote_name],
            cancel_in_progress_transfers=module.params["in_progress"],
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to delete replica link from {0} to {1}:{2}. Error: {3}".format(
                    module.params["name"],
                    remote_name,
                    remote_fs,
                    get_error_message(res),
                )
            )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            target_fs=dict(type="str"),
            target_array=dict(type="str"),
            policy=dict(type="str"),
            in_progress=dict(type="bool", default=False),
            state=dict(default="present", choices=["present", "absent"]),
            link_type=dict(type="str", choices=["full-replica", PARTIAL_REPLICA]),
            replicate_now=dict(type="bool", default=False),
            remote_default_exports=dict(
                type="list", elements="str", choices=["nfs", "smb"]
            ),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    state = module.params["state"]
    policy = module.params["policy"]
    link_type = module.params["link_type"]
    replicate_now = module.params["replicate_now"]
    blade = get_system(module)
    versions = get_rest_api_version(blade)

    # Version and combination gates come first so that nothing is written on
    # an array that cannot honour the request.
    if link_type and LooseVersion(LINK_TYPE_API_VERSION) > LooseVersion(versions):
        module.fail_json(
            msg="link_type requires REST {0} or higher".format(LINK_TYPE_API_VERSION)
        )
    if replicate_now and LooseVersion(LINK_TYPE_API_VERSION) > LooseVersion(versions):
        module.fail_json(
            msg="replicate_now requires REST {0} or higher".format(
                LINK_TYPE_API_VERSION
            )
        )
    if module.params["remote_default_exports"] is not None and LooseVersion(
        REMOTE_EXPORTS_API_VERSION
    ) > LooseVersion(versions):
        module.fail_json(
            msg="remote_default_exports requires REST {0} or higher".format(
                REMOTE_EXPORTS_API_VERSION
            )
        )
    if replicate_now and state == "absent":
        module.fail_json(msg="replicate_now cannot be combined with state=absent")
    if link_type == PARTIAL_REPLICA and policy:
        module.fail_json(msg="Policies cannot be attached to partial-replica links")

    local_fs = get_local_fs(module, blade)
    local_replica_link = get_local_rl(module, blade)

    if not local_fs:
        module.fail_json(
            msg="Selected local filesystem {0} does not exist.".format(
                module.params["name"]
            )
        )

    existing_type = None
    if local_replica_link:
        existing_type = getattr(local_replica_link, "link_type", None)
        if link_type and existing_type and link_type != existing_type:
            module.fail_json(
                msg="Replica link from {0} to {1} is {2}; link_type cannot be changed".format(
                    module.params["name"],
                    local_replica_link.remote.name,
                    existing_type,
                )
            )
    partial_link = existing_type == PARTIAL_REPLICA
    if partial_link and policy:
        module.fail_json(
            msg="Replica link from {0} to {1} is partial-replica; "
            "policies cannot be attached to or removed from partial-replica links".format(
                module.params["name"], local_replica_link.remote.name
            )
        )

    if policy:
        # Replica link policies are snapshot policies; validate against the
        # policies collection, not against links the policy is attached to.
        res = blade.get_policies(names=[policy])
        if res.status_code != 200:
            module.fail_json(msg="Selected policy {0} does not exist.".format(policy))

    if replicate_now:
        if not local_replica_link:
            module.fail_json(
                msg="replicate_now requires an existing replica link for {0}".format(
                    module.params["name"]
                )
            )
        if not partial_link:
            module.fail_json(
                msg="replicate_now is only supported on partial-replica links"
            )
        replicate_rl(module, blade, local_replica_link)

    if state == "present" and not local_replica_link:
        create_rl(module, blade)
    elif state == "present" and local_replica_link and policy:
        add_rl_policy(module, blade, local_replica_link)
    elif state == "absent" and local_replica_link and policy:
        delete_rl_policy(module, blade, local_replica_link)
    elif state == "absent" and local_replica_link:
        if partial_link:
            module.fail_json(
                msg="Replica link from {0} to {1} is partial-replica and cannot be deleted; "
                "destroy and eradicate the replica filesystem {2} on {1} instead".format(
                    module.params["name"],
                    local_replica_link.remote.name,
                    local_replica_link.remote_file_system.name,
                )
            )
        if LooseVersion(DELETE_RL_API_VERSION) > LooseVersion(versions):
            module.fail_json(msg="Deleting a replica link requires REST 2.10 or higher")
        delete_rl(module, blade, local_replica_link)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
