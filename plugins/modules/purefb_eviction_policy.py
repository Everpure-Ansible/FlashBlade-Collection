#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2026, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_eviction_policy
version_added: '1.30.0'
short_description: Manage FlashBlade data eviction policies
description:
- Create, update, rename or delete FlashBlade data eviction policies and
  manage the file systems they are attached to.
- A data eviction policy caps the physical space a Rapid Replica target
  file system keeps locally. Once the file system holds more than
  I(keep_size) of data, the least recently read data is evicted and is
  fetched from the replication source again on demand.
- Policies live on the array that holds the partial replica, so run this
  module against the replication target. Only the target file system of a
  Rapid Replica (partial-replica) link can carry a data eviction policy;
  the array refuses any other file system.
- Requires Purity//FB REST API 2.21 (Purity//FB 4.6.4) or later.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - Name of the data eviction policy.
    type: str
    required: true
  state:
    description:
    - Define whether the policy should exist or not.
    default: present
    choices: [ absent, present ]
    type: str
  enabled:
    description:
    - If C(true) the policy is enabled.
    - Defaults to C(true) on creation if not specified.
    type: bool
  keep_size:
    description:
    - Maximum physical space the target file system may use before the
      least recently read data is evicted.
    - A size with a unit, for example C(100G) or C(2T) (units K, M, G, T
      and P are accepted); a plain integer is taken as bytes.
    - Required when creating a policy. The array enforces its own minimum
      and rejects smaller values.
    type: str
  rename:
    description:
    - New name for the policy.
    - Only takes effect when the policy already exists. If I(name) no
      longer exists but I(rename) does, the rename is treated as already
      applied and the policy is managed under its new name.
    type: str
  file_systems:
    description:
    - Desired set of file systems the policy is attached to.
    - On update the attachments are reconciled against this list - missing
      file systems are attached, extras are detached.
    - Omit to leave existing attachments untouched. Use an empty list to
      detach the policy from every file system.
    - The array only accepts Rapid Replica target file systems.
    type: list
    elements: str
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    type: str
    default: ""
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create a data eviction policy keeping 500G of hot data
  everpure.flashblade.purefb_eviction_policy:
    name: edge_cache
    keep_size: 500G
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Attach the policy to a Rapid Replica target file system
  everpure.flashblade.purefb_eviction_policy:
    name: edge_cache
    file_systems:
      - project_data
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Raise the keep size and disable the policy
  everpure.flashblade.purefb_eviction_policy:
    name: edge_cache
    keep_size: 1T
    enabled: false
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Rename the policy
  everpure.flashblade.purefb_eviction_policy:
    name: edge_cache
    rename: site_b_cache
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Detach the policy from all file systems
  everpure.flashblade.purefb_eviction_policy:
    name: site_b_cache
    file_systems: []
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3

- name: Delete the policy
  everpure.flashblade.purefb_eviction_policy:
    name: site_b_cache
    state: absent
    fb_url: 10.10.10.2
    api_token: T-68618f31-0c9e-4e57-aa44-5306a2cf10e3
"""

RETURN = r"""
policy:
  description:
  - State of the data eviction policy after the task. In check mode this
    is the state before any change, and empty when the policy does not
    exist yet.
  returned: when I(state=present)
  type: dict
  contains:
    name:
      description: Name of the policy.
      type: str
    enabled:
      description: Whether the policy is enabled.
      type: bool
    keep_size:
      description: Maximum physical space kept before eviction, in bytes.
      type: int
    file_systems:
      description: Names of the file systems the policy is attached to.
      type: list
      elements: str
  sample:
    name: edge_cache
    enabled: true
    keep_size: 536870912000
    file_systems:
      - project_data
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        DataEvictionPolicy,
        DataEvictionPolicyPost,
    )
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
    human_to_bytes,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

# Data eviction policies arrived with REST 2.21 (Purity//FB 4.6.4); every
# endpoint used here, context_names included, exists from that version.
MIN_REQUIRED_API_VERSION = "2.21"


def _context_kwargs(module):
    """Return context_names kwargs when a fleet context is set."""
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _keep_size_bytes(module):
    """Return keep_size as an integer number of bytes, or None when unset.

    A plain integer is bytes; anything else goes through human_to_bytes,
    which returns 0 for a value it cannot parse.
    """
    value = module.params["keep_size"]
    if value is None:
        return None
    value = str(value).strip()
    if value.isdigit():
        size = int(value)
    else:
        size = human_to_bytes(value)
    if not size:
        module.fail_json(
            msg=(
                "keep_size {0} is not a valid size. Use a positive size with a "
                "unit such as 100G, or a plain integer number of bytes."
            ).format(module.params["keep_size"])
        )
    return size


def _get_policy(module, blade, name):
    """Return the data eviction policy called C(name), or None."""
    res = blade.get_data_eviction_policies(names=[name], **_context_kwargs(module))
    if res.status_code != 200:
        return None
    items = list(res.items)
    return items[0] if items else None


def _get_members(module, blade):
    """Return the sorted names of the file systems the policy is attached to."""
    res = blade.get_data_eviction_policies_file_systems(
        policy_names=[module.params["name"]], **_context_kwargs(module)
    )
    if res.status_code != 200:
        module.fail_json(
            msg=(
                "Failed to list file systems of data eviction policy {0}. Error: {1}"
            ).format(module.params["name"], get_error_message(res))
        )
    names = []
    for item in list(res.items):
        member_name = getattr(getattr(item, "member", None), "name", None)
        if member_name:
            names.append(member_name)
    return sorted(names)


def _policy_facts(module, blade):
    """Return the policy as a plain dict for the module result."""
    policy = _get_policy(module, blade, module.params["name"])
    if policy is None:
        return {}
    return {
        "name": policy.name,
        "enabled": getattr(policy, "enabled", None),
        "keep_size": getattr(policy, "keep_size", None),
        "file_systems": _get_members(module, blade),
    }


def _attach(module, blade, file_systems, note=""):
    """Attach the policy to each file system, failing on the first refusal.

    The array only accepts Rapid Replica target file systems, so the array's
    own error is surfaced unchanged.
    """
    attached = []
    for fs_name in file_systems:
        res = blade.post_data_eviction_policies_file_systems(
            policy_names=[module.params["name"]],
            member_names=[fs_name],
            **_context_kwargs(module),
        )
        if res.status_code != 200:
            done = " Already attached: {0}.".format(attached) if attached else ""
            module.fail_json(
                msg=(
                    "Failed to attach data eviction policy {0} to file system {1}. "
                    "Error: {2}.{3}{4}"
                ).format(
                    module.params["name"], fs_name, get_error_message(res), done, note
                )
            )
        attached.append(fs_name)


def _detach(module, blade, file_systems):
    """Detach the policy from each file system, failing on the first error."""
    detached = []
    for fs_name in file_systems:
        res = blade.delete_data_eviction_policies_file_systems(
            policy_names=[module.params["name"]],
            member_names=[fs_name],
            **_context_kwargs(module),
        )
        if res.status_code != 200:
            done = " Already detached: {0}.".format(detached) if detached else ""
            module.fail_json(
                msg=(
                    "Failed to detach data eviction policy {0} from file system {1}. "
                    "Error: {2}.{3}"
                ).format(module.params["name"], fs_name, get_error_message(res), done)
            )
        detached.append(fs_name)


def _reconcile_members(module, blade):
    """Reconcile the attached file systems to the desired set.

    Returns True when an attach or detach is (or would be) needed.
    """
    desired = sorted(set(module.params["file_systems"]))
    current = _get_members(module, blade)
    to_attach = [name for name in desired if name not in current]
    to_detach = [name for name in current if name not in desired]
    if not (to_attach or to_detach):
        return False
    if not module.check_mode:
        _attach(module, blade, to_attach)
        _detach(module, blade, to_detach)
    return True


def delete_policy(module, blade):
    """Delete the policy, detaching it from any file systems first."""
    changed = True
    if not module.check_mode:
        attached = _get_members(module, blade)
        _detach(module, blade, attached)
        res = blade.delete_data_eviction_policies(
            names=[module.params["name"]], **_context_kwargs(module)
        )
        if res.status_code != 200:
            note = ""
            if attached:
                note = (
                    " The policy has already been detached from file systems {0};"
                    " re-run to retry the deletion or re-attach them manually."
                ).format(attached)
            module.fail_json(
                msg="Failed to delete data eviction policy {0}. Error: {1}.{2}".format(
                    module.params["name"], get_error_message(res), note
                )
            )
    module.exit_json(changed=changed)


def create_policy(module, blade):
    """Create the policy and attach any requested file systems."""
    keep_size = _keep_size_bytes(module)
    if keep_size is None:
        module.fail_json(
            msg="keep_size is required to create data eviction policy {0}.".format(
                module.params["name"]
            )
        )
    changed = True
    if not module.check_mode:
        post_kwargs = {"keep_size": keep_size}
        if module.params["enabled"] is not None:
            post_kwargs["enabled"] = module.params["enabled"]
        res = blade.post_data_eviction_policies(
            names=[module.params["name"]],
            policy=DataEvictionPolicyPost(**post_kwargs),
            **_context_kwargs(module),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Failed to create data eviction policy {0}. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
        if module.params["file_systems"]:
            _attach(
                module,
                blade,
                sorted(set(module.params["file_systems"])),
                note=" The policy was created; fix file_systems and re-run.",
            )
    module.exit_json(changed=changed, policy=_policy_facts(module, blade))


def update_policy(module, blade, policy):
    """Update the policy's settings, attachments and name."""
    changed = False

    # Validate the parameters and build the PATCH body before any member
    # attach or detach is sent, so a bad keep_size fails without writes.
    patch_kwargs = {}
    if module.params["enabled"] is not None and module.params["enabled"] != getattr(
        policy, "enabled", None
    ):
        patch_kwargs["enabled"] = module.params["enabled"]

    keep_size = _keep_size_bytes(module)
    if keep_size is not None and keep_size != getattr(policy, "keep_size", None):
        patch_kwargs["keep_size"] = keep_size

    if module.params["rename"] and module.params["rename"] != getattr(
        policy, "name", None
    ):
        patch_kwargs["name"] = module.params["rename"]

    if module.params["file_systems"] is not None:
        # Reconcile under the current name; a rename is applied afterwards
        # so the member calls address a policy that still exists.
        if _reconcile_members(module, blade):
            changed = True

    if patch_kwargs:
        changed = True
        if not module.check_mode:
            res = blade.patch_data_eviction_policies(
                names=[module.params["name"]],
                policy=DataEvictionPolicy(**patch_kwargs),
                **_context_kwargs(module),
            )
            if res.status_code != 200:
                module.fail_json(
                    msg="Failed to update data eviction policy {0}. Error: {1}".format(
                        module.params["name"], get_error_message(res)
                    )
                )
            if "name" in patch_kwargs:
                module.params["name"] = patch_kwargs["name"]

    module.exit_json(changed=changed, policy=_policy_facts(module, blade))


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            state=dict(type="str", default="present", choices=["absent", "present"]),
            name=dict(type="str", required=True),
            enabled=dict(type="bool"),
            keep_size=dict(type="str"),
            rename=dict(type="str"),
            file_systems=dict(type="list", elements="str"),
            context=dict(type="str", default=""),
        )
    )

    module = AnsibleModule(argument_spec, supports_check_mode=True)

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="FlashBlade REST version not supported. "
            "Minimum version required: {0}".format(MIN_REQUIRED_API_VERSION)
        )

    state = module.params["state"]
    policy = _get_policy(module, blade, module.params["name"])

    if state == "present" and policy is None and module.params["rename"]:
        # The rename may already have happened on an earlier run: when a
        # policy with the new name exists, manage it under that name and
        # treat the rename as done so a repeated rename task is idempotent.
        policy = _get_policy(module, blade, module.params["rename"])
        if policy is None:
            module.fail_json(
                msg="Cannot rename data eviction policy {0}: policy does not exist.".format(
                    module.params["name"]
                )
            )
        module.params["name"] = module.params["rename"]

    if state == "present" and policy is None:
        create_policy(module, blade)
    elif state == "present":
        update_policy(module, blade, policy)
    elif state == "absent" and policy is not None:
        delete_policy(module, blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
