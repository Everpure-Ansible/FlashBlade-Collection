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
module: purefb_tgroup
version_added: '1.30.0'
short_description: Manage Fusion topology groups on Everpure FlashBlades
description:
- Create, delete or modify Fusion topology groups from an Everpure FlashBlade.
- Supports topology group rename, moving a group under a different parent,
  and adding or removing array and child topology group members.
- Topology groups are fleet-scoped objects, so the FlashBlade must be a
  member of a fleet (see M(everpure.flashblade.purefb_fleet)).
- Requires FlashBlade REST API version 2.26 or later (Purity//FB 4.8.1+).
- Creating, modifying or deleting topology groups and their members requires
  the API token of a directory-backed (LDAP or SAML) user. The array rejects
  local users and API clients (C(Operation not permitted) or HTTP 403); the
  module reports that requirement alongside the array's error.
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@everpuredata.com>
options:
  name:
    description:
    - The name of the topology group.
    type: str
    required: true
  state:
    description:
    - Define whether the topology group should exist or not.
    - With I(state=absent) and I(array) or I(tgroup) set, only those members
      are removed from the topology group; the group itself is kept.
    - With I(state=absent) and no members given the topology group is
      deleted. The array refuses to delete a group that still has members
      or is referenced by a preset; remove the members first.
    - Member names given with I(state=absent) that are not current members
      are ignored.
    type: str
    default: present
    choices: [ absent, present ]
  rename:
    description:
    - New name of the topology group.
    - A rename and a parent move are sent as separate requests because the
      array cannot do both in one call.
    - When I(name) no longer exists but I(rename) does, the rename is treated
      as complete and the remaining options are applied to the renamed group.
    type: str
  parent:
    description:
    - Parent topology group name.
    - The parent must already exist.
    type: str
  array:
    description:
    - List of fleet member arrays (FlashBlade or FlashArray) to add to or
      remove from the topology group.
    - Each name must be an array in the same fleet as the FlashBlade
      receiving the request.
    type: list
    elements: str
  tgroup:
    description:
    - List of existing child topology groups to add to or remove from
      the topology group.
    type: list
    elements: str
  context:
    description:
    - Name of fleet member on which to perform the operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    - Only sent to the array when set. Purity//FB may refuse a context on
      the topology group endpoints (REST 2.30 answers C(Parameter
      context_names is not supported in the target version)); the module
      then fails with that error and a hint to omit I(context). Fleet
      membership and array lookups are never context-scoped.
    type: str
    default: ""
extends_documentation_fragment:
- everpure.flashblade.everpure.fb
"""

EXAMPLES = r"""
- name: Create a topology group
  everpure.flashblade.purefb_tgroup:
    name: app-stack
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Create a child topology group under an existing parent
  everpure.flashblade.purefb_tgroup:
    name: app-stack-dev
    parent: app-stack
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Rename a topology group
  everpure.flashblade.purefb_tgroup:
    name: app-stack-dev
    rename: app-stack-qa
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Add array and child topology group members
  everpure.flashblade.purefb_tgroup:
    name: app-stack
    array:
      - flashblade-a
      - flasharray-b
    tgroup:
      - app-stack-qa
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Remove specific members from a topology group
  everpure.flashblade.purefb_tgroup:
    name: app-stack
    array:
      - flasharray-b
    tgroup:
      - app-stack-qa
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641

- name: Delete a topology group
  everpure.flashblade.purefb_tgroup:
    name: app-stack-dev
    state: absent
    fb_url: 10.10.10.2
    api_token: T-55a68eb5-c785-4720-a2ca-8b03903bf641
"""

RETURN = r"""
"""

HAS_PYPURECLIENT = True
try:
    from pypureclient.flashblade import (
        NewName,
        ReferenceWritable,
        TgroupMembersPost,
        TgroupMembersPostMember,
        TgroupPatch,
    )
except ImportError:
    HAS_PYPURECLIENT = False

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.everpure.flashblade.plugins.module_utils.purefb import (
    get_system,
    purefb_argument_spec,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.common import (
    get_rest_api_version,
)
from ansible_collections.everpure.flashblade.plugins.module_utils.version import (
    LooseVersion,
)

MIN_REQUIRED_API_VERSION = "2.26"
PERMISSION_HINT = (
    "Topology group changes require the API token of a directory-backed "
    "(LDAP or SAML) user; local users and API clients are not permitted."
)
CONTEXT_HINT = (
    "The array does not accept a context for topology groups on this "
    "Purity//FB version; retry without the context option."
)
NOT_FOUND_MARKERS = ("does not exist", "not found")


def _context_kwargs(module):
    """Return context_names kwargs only when the user set a context.

    The SDK advertises context_names on every topology group call from
    REST 2.26, but Purity//FB (REST 2.30 included) refuses the parameter
    with "Parameter context_names is not supported in the target version",
    so nothing is sent unless asked for and a refusal is reported with
    CONTEXT_HINT by fail_on_error.
    """
    if module.params["context"]:
        return {"context_names": [module.params["context"]]}
    return {}


def _is_not_found(res):
    """True when a 400 says the named object is missing, not that it was refused."""
    error_text = _error_text(res).lower()
    return any(marker in error_text for marker in NOT_FOUND_MARKERS)


def _extract_members(members, resource_type):
    return [
        member.member.name
        for member in members
        if getattr(getattr(member, "member", None), "resource_type", None)
        == resource_type
        and getattr(getattr(member, "member", None), "name", None)
    ]


def _missing_names(requested_names, items):
    found_names = {
        getattr(item, "name", None) for item in items if getattr(item, "name", None)
    }
    return sorted(set(requested_names or []).difference(found_names))


def _error_text(res):
    """Render every error of an ErrorResponse, message and context included.

    Topology group errors often carry the useful detail in `context` while
    `message` is None, so reporting only errors[0].message loses the cause.
    """
    parts = []
    for err in getattr(res, "errors", None) or []:
        message = getattr(err, "message", None)
        context = getattr(err, "context", None)
        if message and context:
            parts.append("{0} ({1})".format(message, context))
        elif message or context:
            parts.append(str(message or context))
    if not parts:
        return "HTTP {0} with no error detail".format(
            getattr(res, "status_code", "unknown")
        )
    return "; ".join(parts)


def fail_on_error(res, module, operation):
    """Fail the module with the full error list when a response is not 200."""
    status_code = getattr(res, "status_code", None)
    if isinstance(status_code, int) and status_code != 200:
        error_text = _error_text(res)
        msg = "{0}. Error: {1}".format(operation, error_text)
        # FlashArray refuses a local identity with 403; Purity//FB answers
        # 400 "Operation not permitted." for the same reason.
        lowered = error_text.lower()
        if status_code == 403 or "operation not permitted" in lowered:
            msg = "{0} {1}".format(msg, PERMISSION_HINT)
        # Purity//FB refuses context_names on the topology group endpoints
        if "context_names" in lowered and "not supported" in lowered:
            msg = "{0} {1}".format(msg, CONTEXT_HINT)
        module.fail_json(msg=msg, status_code=status_code, changed=False)


def check_fleet_membership(module, blade):
    """Topology groups describe fleet topology; fail early outside a fleet."""
    res = blade.get_fleets()
    status_code = getattr(res, "status_code", None)
    if status_code == 404:
        module.fail_json(msg="Fusion is not enabled on this system.")
    if status_code != 200:
        module.fail_json(
            msg="Failed to read fleet membership. Error: {0}".format(_error_text(res))
        )
    if not list(res.items):
        module.fail_json(
            msg="Topology groups require the array to be a member of a fleet."
        )


def get_tgroup(module, blade, name=None):
    tgroup_name = name or module.params["name"]
    res = blade.get_topology_groups(names=[tgroup_name], **_context_kwargs(module))
    if res.status_code == 200:
        items = list(res.items)
        if items:
            return items[0]
        return None
    # Purity//FB answers an unknown name with 200 and no items; FlashArray
    # answers 400 "... does not exist".  Every other error (a refused
    # identity, an unsupported context, a bad query) is a failed read, never
    # "not found", or state=absent would report ok and state=present would
    # try to create a group that may already exist.
    if res.status_code == 400 and _is_not_found(res):
        return None
    fail_on_error(res, module, "Failed to read topology group {0}".format(tgroup_name))
    return None


def get_tgroup_members(module, blade, name=None):
    tgroup_name = name or module.params["name"]
    res = blade.get_topology_groups_members(
        topology_group_names=[tgroup_name], **_context_kwargs(module)
    )
    # Only called for a group that exists, so any refusal is a real failure
    fail_on_error(
        res,
        module,
        "Failed to read members of topology group {0}".format(tgroup_name),
    )
    return list(res.items)


def rename_exists(module, blade):
    return get_tgroup(module, blade, module.params["rename"]) is not None


def _build_members_payload(array_members=None, child_tgroups=None):
    members = []
    for array_member in sorted(set(array_members or [])):
        members.append(
            TgroupMembersPostMember(
                member=ReferenceWritable(
                    name=array_member,
                    resource_type="remote-arrays",
                )
            )
        )
    for child_tgroup in sorted(set(child_tgroups or [])):
        members.append(
            TgroupMembersPostMember(
                member=ReferenceWritable(
                    name=child_tgroup, resource_type="topology-groups"
                )
            )
        )
    return TgroupMembersPost(members=members)


def add_members(module, blade, tgroup_name, array_members=None, child_tgroups=None):
    if not (array_members or child_tgroups):
        return
    res = blade.post_topology_groups_members(
        topology_group_names=[tgroup_name],
        members=_build_members_payload(array_members, child_tgroups),
        **_context_kwargs(module)
    )
    fail_on_error(
        res,
        module,
        "Failed to add members to topology group {0}".format(tgroup_name),
    )


def remove_members(module, blade, tgroup_name, member_names):
    if not member_names:
        return
    res = blade.delete_topology_groups_members(
        topology_group_names=[tgroup_name],
        member_names=member_names,
        **_context_kwargs(module)
    )
    fail_on_error(
        res,
        module,
        "Failed to remove members from topology group {0}".format(tgroup_name),
    )


def validate_inputs(module, blade, current_tgroup=None, current_members=None):
    requested_children = module.params["tgroup"] or []
    requested_parent = module.params["parent"]
    adding = module.params["state"] == "present"
    current_arrays = _extract_members(current_members or [], "remote-arrays")
    current_child_tgroups = _extract_members(current_members or [], "topology-groups")
    invalid_self_refs = {module.params["name"]}
    if module.params["rename"]:
        invalid_self_refs.add(module.params["rename"])

    if requested_parent:
        if requested_parent in invalid_self_refs:
            module.fail_json(msg="A topology group cannot be its own parent.")
        if requested_parent in requested_children:
            module.fail_json(
                msg=(
                    "A topology group cannot use the same topology group "
                    "as both parent and child member."
                )
            )
        if not get_tgroup(module, blade, requested_parent):
            module.fail_json(
                msg="Parent topology group {0} does not exist.".format(requested_parent)
            )
        if current_tgroup and requested_parent in current_child_tgroups:
            module.fail_json(
                msg=(
                    "Cannot move topology group {0} under direct child "
                    "topology group {1}."
                ).format(module.params["name"], requested_parent)
            )

    if requested_children:
        for child_tgroup in requested_children:
            if child_tgroup in invalid_self_refs:
                module.fail_json(
                    msg="A topology group cannot be a child member of itself."
                )
        # Names already in the group need no lookup, and with state=absent a
        # name that is not a member is a no-op; only additions are checked.
        new_children = sorted(set(requested_children).difference(current_child_tgroups))
        if adding and new_children:
            res = blade.get_topology_groups(
                names=new_children, **_context_kwargs(module)
            )
            fail_on_error(res, module, "Child topology group not found")
            missing_children = _missing_names(new_children, list(res.items))
            if missing_children:
                module.fail_json(
                    msg="Child topology group not found: {0}".format(
                        ", ".join(missing_children)
                    )
                )

    new_arrays = sorted(set(module.params["array"] or []).difference(current_arrays))
    if adding and new_arrays:
        # current_fleet_only is mandatory on FlashBlade
        res = blade.get_remote_arrays(current_fleet_only=True)
        fail_on_error(res, module, "Array not found")
        missing_arrays = _missing_names(new_arrays, list(res.items))
        if missing_arrays:
            module.fail_json(
                msg="Array not found: {0}".format(", ".join(missing_arrays))
            )


def create_tgroup(module, blade):
    if module.params["rename"]:
        module.fail_json(
            msg="Topology group {0} does not exist - rename failed.".format(
                module.params["name"]
            )
        )

    changed = True
    if not module.check_mode:
        kwargs = {"names": [module.params["name"]]}
        if module.params["parent"]:
            kwargs["parent_topology_group_names"] = [module.params["parent"]]
        kwargs.update(_context_kwargs(module))
        res = blade.post_topology_groups(**kwargs)
        fail_on_error(
            res,
            module,
            "Failed to create topology group {0}".format(module.params["name"]),
        )
        add_members(
            module,
            blade,
            module.params["name"],
            module.params["array"],
            module.params["tgroup"],
        )
    module.exit_json(changed=changed)


def update_tgroup(module, blade, tgroup, members):
    changed = False
    current_name = tgroup.name
    current_parent = getattr(
        getattr(tgroup, "parent_topology_group", None), "name", None
    )
    current_arrays = _extract_members(members, "remote-arrays")
    current_child_tgroups = _extract_members(members, "topology-groups")

    if module.params["state"] == "present":
        if module.params["rename"] and module.params["rename"] != current_name:
            if not rename_exists(module, blade):
                changed = True
                if not module.check_mode:
                    res = blade.patch_topology_groups(
                        names=[current_name],
                        topology_group=TgroupPatch(
                            topology_group=NewName(name=module.params["rename"])
                        ),
                        **_context_kwargs(module)
                    )
                    fail_on_error(
                        res,
                        module,
                        "Failed to rename topology group {0} to {1}".format(
                            current_name, module.params["rename"]
                        ),
                    )
                current_name = module.params["rename"]
            else:
                module.warn(
                    "Rename failed. Topology group {0} already exists. "
                    "Continuing with other changes...".format(module.params["rename"])
                )

        if module.params["parent"] and module.params["parent"] != current_parent:
            changed = True
            if not module.check_mode:
                # The array cannot rename and move in one request
                res = blade.patch_topology_groups(
                    names=[current_name],
                    topology_group=TgroupPatch(),
                    to_parent_topology_group_names=[module.params["parent"]],
                    **_context_kwargs(module)
                )
                fail_on_error(
                    res,
                    module,
                    "Failed to move topology group {0} under parent {1}".format(
                        current_name, module.params["parent"]
                    ),
                )

        new_arrays = sorted(
            set(module.params["array"] or []).difference(set(current_arrays))
        )
        new_tgroups = sorted(
            set(module.params["tgroup"] or []).difference(set(current_child_tgroups))
        )
        if new_arrays or new_tgroups:
            changed = True
            if not module.check_mode:
                add_members(module, blade, current_name, new_arrays, new_tgroups)
    else:
        old_arrays = sorted(
            set(module.params["array"] or []).intersection(set(current_arrays))
        )
        old_tgroups = sorted(
            set(module.params["tgroup"] or []).intersection(set(current_child_tgroups))
        )
        if old_arrays or old_tgroups:
            changed = True
            if not module.check_mode:
                remove_members(module, blade, current_name, old_arrays + old_tgroups)

    module.exit_json(changed=changed)


def delete_tgroup(module, blade):
    changed = True
    if not module.check_mode:
        res = blade.delete_topology_groups(
            names=[module.params["name"]], **_context_kwargs(module)
        )
        fail_on_error(
            res,
            module,
            "Failed to delete topology group {0}".format(module.params["name"]),
        )
    module.exit_json(changed=changed)


def main():
    argument_spec = purefb_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(type="str", default="present", choices=["absent", "present"]),
            rename=dict(type="str"),
            parent=dict(type="str"),
            array=dict(type="list", elements="str"),
            tgroup=dict(type="list", elements="str"),
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
            msg=(
                "FlashBlade REST version not supported. "
                "Minimum version required: {0} (Purity//FB 4.8.1+)"
            ).format(MIN_REQUIRED_API_VERSION)
        )
    check_fleet_membership(module, blade)

    state = module.params["state"]
    current_tgroup = get_tgroup(module, blade)
    if current_tgroup is None and state == "present" and module.params["rename"]:
        # A rename completed on an earlier run left the group under its new
        # name; converge parent and members against that group.
        current_tgroup = get_tgroup(module, blade, module.params["rename"])
    current_members = (
        get_tgroup_members(module, blade, current_tgroup.name) if current_tgroup else []
    )
    validate_inputs(module, blade, current_tgroup, current_members)

    if current_tgroup and state == "present":
        update_tgroup(module, blade, current_tgroup, current_members)
    elif (
        current_tgroup
        and state == "absent"
        and (module.params["array"] or module.params["tgroup"])
    ):
        update_tgroup(module, blade, current_tgroup, current_members)
    elif current_tgroup and state == "absent":
        delete_tgroup(module, blade)
    elif current_tgroup is None and state == "absent":
        module.exit_json(changed=False)
    else:
        create_tgroup(module, blade)

    module.exit_json(changed=False)


if __name__ == "__main__":
    main()
