#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2018, Simon Dodsley (simon@everpuredata.com)
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
module: purefb_dsrole
version_added: '1.0.0'
short_description: Configure FlashBlade Management Directory Service Roles
description:
- Create, update or delete directory service role mappings. A mapping ties a
  directory service group to the management access policies, or the legacy
  role, that its members receive on the FlashBlade.
- The built-in mappings C(array_admin), C(ops_admin), C(readonly) and
  C(storage_admin) are updated in place and cleared, rather than deleted,
  with I(state=absent). A built-in mapping missing from the array is created.
- Any other I(name) is a custom mapping, which is created and deleted.
- Requires FlashBlade REST API version 2.14 or later (Purity//FB 4.4.2+).
  I(policies) requires REST API version 2.19 or later (Purity//FB 4.6.1+).
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  state:
    description:
    - Create or delete directory service role
    default: present
    type: str
    choices: [ absent, present ]
  name:
    description:
    - Name of the directory service role mapping.
    - Defaults to I(role), which addresses the built-in mapping of that name.
    - One of I(name) or I(role) is required.
    type: str
    version_added: '1.30.0'
  role:
    description:
    - The legacy role granted by the mapping. Ensures the management access
      policy of the same name is attached to the mapping; other attached
      policies are left in place. Use I(policies) to set the exact policy
      set.
    - Below REST API version 2.19 the array replaces the mapping's single
      role instead.
    - Mutually exclusive with I(policies). One of I(role) or I(policies) is
      required with I(state=present).
    choices: [ array_admin, ops_admin, readonly, storage_admin ]
    type: str
  policies:
    description:
    - List of management access policy names granted by the mapping.
    - The mapping's policy set is reconciled to this list. Policies are
      attached before any are detached, and names are compared
      case-insensitively. At least one policy is required.
    - Requires REST API version 2.19 or later.
    - Mutually exclusive with I(role).
    type: list
    elements: str
    version_added: '1.30.0'
  group_base:
    description:
    - Specifies where the configured group is located in the directory
      tree. This field consists of Organizational Units (OUs) that combine
      with the base DN attribute and the configured group CNs to complete
      the full Distinguished Name of the groups. The group base should
      specify OU= for each OU and multiple OUs should be separated by commas.
      The order of OUs is important and should get larger in scope from left
      to right.
    - Each OU should not exceed 64 characters in length.
    - Compared case-insensitively with the array's value.
    type: str
  group:
    description:
    - Sets the common Name (CN) of the configured directory service group
      containing users for the FlashBlade. This name should be just the
      Common Name of the group without the CN= specifier.
    - Common Names should not exceed 64 characters in length.
    - Compared case-insensitively with the array's value.
    type: str
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Delete existing array_admin directory service role
  everpure.flashblade.purefb_dsrole:
    role: array_admin
    state: absent
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Create array_admin directory service role
  everpure.flashblade.purefb_dsrole:
    role: array_admin
    group_base: "OU=PureGroups,OU=SANManagers"
    group: pureadmins
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Update ops_admin directory service role
  everpure.flashblade.purefb_dsrole:
    role: ops_admin
    group_base: "OU=PureGroups"
    group: opsgroup
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Create a custom mapping granting two management access policies
  everpure.flashblade.purefb_dsrole:
    name: nfs-operators
    group_base: "OU=PureGroups"
    group: nfs-ops
    policies:
      - readonly
      - nfs_admins
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Create a custom mapping granting a legacy role
  everpure.flashblade.purefb_dsrole:
    name: auditors
    group_base: "OU=PureGroups"
    group: audit
    role: readonly
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Delete a custom mapping
  everpure.flashblade.purefb_dsrole:
    name: nfs-operators
    state: absent
    fb_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
"""

RETURN = r"""
"""


HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        DirectoryServiceRole,
        DirectoryServiceRolePost,
        ReferenceWritable,
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
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

MIN_REQUIRED_API_VERSION = "2.14"
MIN_POLICIES_API_VERSION = "2.19"
BUILTIN_ROLES = ["array_admin", "ops_admin", "readonly", "storage_admin"]


def _current_policy_names(mapping):
    """Return the management access policy names attached to a mapping.

    ``management_access_policies`` is reported from REST 2.19. Older arrays
    only report the legacy ``role``, which stands for the policy of the same
    name.
    """
    policies = getattr(mapping, "management_access_policies", None)
    if policies is not None:
        return [pol.name for pol in policies if getattr(pol, "name", None)]
    role_name = getattr(getattr(mapping, "role", None), "name", None)
    return [role_name] if role_name else []


def _policy_diff(current, desired):
    """Return (to_add, to_remove), comparing names case-insensitively.

    Additions use the requested spelling, removals the array's spelling.
    """
    current_by_key = {name.lower(): name for name in current}
    desired_by_key = {}
    for name in desired:
        desired_by_key.setdefault(name.lower(), name)
    to_add = [name for key, name in desired_by_key.items() if key not in current_by_key]
    to_remove = [
        name for key, name in current_by_key.items() if key not in desired_by_key
    ]
    return sorted(to_add), sorted(to_remove)


def _desired_policies(module):
    """The policy set the mapping should hold: policies, or the single role"""
    if module.params["policies"] is not None:
        return module.params["policies"]
    return [module.params["role"]]


def _dn_changed(current, requested):
    """True when a requested group or group_base differs from the array's.

    An omitted parameter is never compared. The array normalises the case
    of distinguished-name components, so the comparison ignores case.
    """
    if requested is None:
        return False
    return (current or "").lower() != requested.lower()


def _get_mapping(module, blade):
    """Return the mapping, or None when the array reports it missing.

    A missing name is a 400 whose message says the role does not exist;
    any other error is fatal.
    """
    name = module.params["name"]
    res = blade.get_directory_services_roles(names=[name])
    if res.status_code == 200:
        items = list(res.items)
        return items[0] if items else None
    error = get_error_message(res)
    if res.status_code == 400 and "does not exist" in str(error).lower():
        return None
    module.fail_json(
        msg="Fetch Directory Service Role {0} failed. Error: {1}".format(name, error)
    )


def _patch_mapping(module, blade, body, action):
    res = blade.patch_directory_services_roles(
        names=[module.params["name"]], directory_service_roles=body
    )
    if res.status_code != 200:
        module.fail_json(
            msg="{0} Directory Service Role {1} failed. Error: {2}".format(
                action, module.params["name"], get_error_message(res)
            )
        )


def _reconcile_policies(module, blade, to_add, to_remove):
    """Attach the missing policies, then detach the surplus ones.

    Attaching first keeps at least one policy on the mapping throughout.
    """
    name = module.params["name"]
    if to_add:
        res = blade.post_management_access_policies_directory_services_roles(
            member_names=[name], policy_names=to_add
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Attaching policies {0} to Directory Service Role {1} failed. "
                "Error: {2}".format(to_add, name, get_error_message(res))
            )
    if to_remove:
        res = blade.delete_management_access_policies_directory_services_roles(
            member_names=[name], policy_names=to_remove
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Detaching policies {0} from Directory Service Role {1} failed. "
                "Error: {2}".format(to_remove, name, get_error_message(res))
            )


def update_mapping(module, blade, mapping, policies_supported):
    """Update Directory Service Role mapping"""
    dn_changed = _dn_changed(
        getattr(mapping, "group", None), module.params["group"]
    ) or _dn_changed(getattr(mapping, "group_base", None), module.params["group_base"])
    to_add, to_remove = _policy_diff(
        _current_policy_names(mapping), _desired_policies(module)
    )
    if module.params["policies"] is None and policies_supported:
        # role only ensures its policy is attached; other policies on the
        # mapping, e.g. attached with purefb_mgmt_role, are left in place.
        to_remove = []
    if not (dn_changed or to_add or to_remove):
        module.exit_json(changed=False)
    if module.check_mode:
        module.exit_json(changed=True)

    patch_kwargs = {}
    if dn_changed:
        patch_kwargs["group"] = module.params["group"]
        patch_kwargs["group_base"] = module.params["group_base"]
    if (to_add or to_remove) and not policies_supported:
        # Below REST 2.19 the policy set is only reachable through the
        # legacy role field, which replaces it with the named role.
        patch_kwargs["role"] = ReferenceWritable(name=module.params["role"])
    if patch_kwargs:
        _patch_mapping(module, blade, DirectoryServiceRole(**patch_kwargs), "Update")
    if (to_add or to_remove) and policies_supported:
        _reconcile_policies(module, blade, to_add, to_remove)
    module.exit_json(changed=True)


def delete_mapping(module, blade, mapping):
    """Delete a custom mapping, or clear the group of a built-in one"""
    name = module.params["name"]
    if name in BUILTIN_ROLES:
        if not (
            getattr(mapping, "group", None) or getattr(mapping, "group_base", None)
        ):
            module.exit_json(changed=False)
        if not module.check_mode:
            _patch_mapping(
                module, blade, DirectoryServiceRole(group_base="", group=""), "Delete"
            )
        module.exit_json(changed=True)
    if not module.check_mode:
        res = blade.delete_directory_services_roles(names=[name])
        if res.status_code != 200:
            module.fail_json(
                msg="Delete Directory Service Role {0} failed. Error: {1}".format(
                    name, get_error_message(res)
                )
            )
    module.exit_json(changed=True)


def create_mapping(module, blade, policies_supported):
    """Create Directory Service Role mapping"""
    if not module.check_mode:
        body = {
            "group": module.params["group"],
            "group_base": module.params["group_base"],
        }
        if policies_supported:
            body["management_access_policies"] = [
                ReferenceWritable(name=policy) for policy in _desired_policies(module)
            ]
        else:
            body["role"] = ReferenceWritable(name=module.params["role"])
        res = blade.post_directory_services_roles(
            names=[module.params["name"]],
            directory_service_roles=DirectoryServiceRolePost(**body),
        )
        if res.status_code != 200:
            module.fail_json(
                msg="Create Directory Service Role {0} failed. Error: {1}".format(
                    module.params["name"], get_error_message(res)
                )
            )
    module.exit_json(changed=True)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str"),
            role=dict(type="str", choices=BUILTIN_ROLES),
            policies=dict(type="list", elements="str"),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            group_base=dict(type="str"),
            group=dict(type="str"),
        )
    )

    module = AnsibleModule(
        argument_spec,
        required_together=[["group", "group_base"]],
        required_one_of=[["name", "role"]],
        mutually_exclusive=[["role", "policies"]],
        required_if=[["state", "present", ["role", "policies"], True]],
        supports_check_mode=True,
    )

    if not HAS_PYPURECLIENT:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    if not module.params["name"]:
        module.params["name"] = module.params["role"]
    state = module.params["state"]
    if state == "present" and module.params["policies"] == []:
        module.fail_json(msg="policies must name at least one management access policy")

    blade = get_system(module)
    api_version = get_rest_api_version(blade)
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg=(
                "FlashBlade REST version not supported. "
                "Minimum version required: {0} (Purity//FB 4.4.2+)"
            ).format(MIN_REQUIRED_API_VERSION)
        )
    policies_supported = LooseVersion(MIN_POLICIES_API_VERSION) <= LooseVersion(
        api_version
    )
    if module.params["policies"] is not None and not policies_supported:
        module.fail_json(
            msg=(
                "policies requires FlashBlade REST version {0} or later "
                "(Purity//FB 4.6.1+)"
            ).format(MIN_POLICIES_API_VERSION)
        )

    mapping = _get_mapping(module, blade)
    if state == "absent":
        if mapping is None:
            module.exit_json(changed=False)
        delete_mapping(module, blade, mapping)
    elif mapping is None:
        create_mapping(module, blade, policies_supported)
    else:
        update_mapping(module, blade, mapping, policies_supported)


if __name__ == "__main__":
    main()
